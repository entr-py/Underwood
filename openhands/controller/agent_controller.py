# IMPORTANT: LEGACY V0 CODE - Deprecated since version 1.0.0, scheduled for removal April 1, 2026
# This file is part of the legacy (V0) implementation of OpenHands and will be removed soon as we complete the migration to V1.
# OpenHands V1 uses the Software Agent SDK for the agentic core and runs a new application server. Please refer to:
#   - V1 agentic core (SDK): https://github.com/OpenHands/software-agent-sdk
#   - V1 application server (in this repo): openhands/app_server/
# Unless you are working on deprecation, please avoid extending this legacy file and consult the V1 codepaths above.
# Tag: Legacy-V0
# V1 replacement for this module lives in the Software Agent SDK.
from __future__ import annotations

import asyncio
import copy
import json
import os
import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from openhands.security.analyzer import SecurityAnalyzer

from litellm.exceptions import (  # noqa
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    ContentPolicyViolationError,
    ContextWindowExceededError,
    InternalServerError,
    NotFoundError,
    OpenAIError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from openhands.controller.agent import Agent
from openhands.controller.replay import ReplayManager
from openhands.controller.state.state import State, ToolPermissionContext
from openhands.controller.state.state_tracker import StateTracker
from openhands.controller.stuck import StuckDetector
from openhands.core.config import AgentConfig, LLMConfig
from openhands.core.exceptions import (
    AgentStuckInLoopError,
    FunctionCallNotExistsError,
    FunctionCallValidationError,
    LLMContextWindowExceedError,
    LLMMalformedActionError,
    LLMNoActionError,
    LLMResponseError,
)
from openhands.core.logger import LOG_ALL_EVENTS
from openhands.core.logger import openhands_logger as logger
from openhands.core.schema import AgentState
from openhands.events import (
    EventSource,
    EventStream,
    EventStreamSubscriber,
    RecallType,
)
from openhands.events.action import (
    Action,
    ActionConfirmationStatus,
    ActionSecurityRisk,
    AgentDelegateAction,
    AgentFinishAction,
    AgentRejectAction,
    BrowseInteractiveAction,
    BrowseURLAction,
    ChangeAgentStateAction,
    CmdRunAction,
    FileEditAction,
    FileReadAction,
    FileWriteAction,
    IPythonRunCellAction,
    MCPAction,
    MessageAction,
    NullAction,
    SystemMessageAction,
    LoopRecoveryAction,
)
from openhands.events.action.agent import (
    CondensationAction,
    CondensationRequestAction,
    RecallAction,
)
from openhands.events.event import Event
from openhands.events.observation import (
    AgentDelegateObservation,
    AgentStateChangedObservation,
    ErrorObservation,
    NullObservation,
    Observation,
    LoopDetectionObservation,
    CmdOutputObservation,
)
from openhands.events.serialization.event import truncate_content
from openhands.llm.metrics import Metrics
from openhands.runtime.runtime_status import RuntimeStatus
from openhands.server.services.conversation_stats import ConversationStats
from openhands.storage.files import FileStore

# note: RESUME is only available on web GUI
TRAFFIC_CONTROL_REMINDER = (
    "Please click on resume button if you'd like to continue, or start a new task."
)
ERROR_ACTION_NOT_EXECUTED_STOPPED_ID = 'AGENT_ERROR$ERROR_ACTION_NOT_EXECUTED_STOPPED'
ERROR_ACTION_NOT_EXECUTED_ERROR_ID = 'AGENT_ERROR$ERROR_ACTION_NOT_EXECUTED_ERROR'
ERROR_ACTION_NOT_EXECUTED_STOPPED = (
    'Stop button pressed. The action has not been executed.'
)
ERROR_ACTION_NOT_EXECUTED_ERROR = 'The action has not been executed due to a runtime error. The runtime system may have crashed and restarted due to resource constraints. Any previously established system state, dependencies, or environment variables may have been lost.'


class AgentController:
    id: str
    agent: Agent
    max_iterations: int
    event_stream: EventStream
    state: State
    confirmation_mode: bool
    agent_to_llm_config: dict[str, LLMConfig]
    agent_configs: dict[str, AgentConfig]
    parent: 'AgentController | None' = None
    delegate: 'AgentController | None' = None
    _pending_action_info: tuple[Action, float] | None = None  # (action, timestamp)
    _closed: bool = False
    _cached_first_user_message: MessageAction | None = None
    _validation_triggered: bool = False
    _validation_completed: bool = False

    def __init__(
        self,
        agent: Agent,
        event_stream: EventStream,
        conversation_stats: ConversationStats,
        iteration_delta: int,
        budget_per_task_delta: float | None = None,
        agent_to_llm_config: dict[str, LLMConfig] | None = None,
        agent_configs: dict[str, AgentConfig] | None = None,
        sid: str | None = None,
        file_store: FileStore | None = None,
        user_id: str | None = None,
        confirmation_mode: bool = False,
        initial_state: State | None = None,
        is_delegate: bool = False,
        headless_mode: bool = True,
        status_callback: Callable | None = None,
        replay_events: list[Event] | None = None,
        security_analyzer: 'SecurityAnalyzer | None' = None,
    ):
        """Initializes a new instance of the AgentController class.

        Args:
            agent: The agent instance to control.
            event_stream: The event stream to publish events to.
            max_iterations: The maximum number of iterations the agent can run.
            max_budget_per_task: The maximum budget (in USD) allowed per task, beyond which the agent will stop.
            agent_to_llm_config: A dictionary mapping agent names to LLM configurations in the case that
                we delegate to a different agent.
            agent_configs: A dictionary mapping agent names to agent configurations in the case that
                we delegate to a different agent.
            sid: The session ID of the agent.
            confirmation_mode: Whether to enable confirmation mode for agent actions.
            initial_state: The initial state of the controller.
            is_delegate: Whether this controller is a delegate.
            headless_mode: Whether the agent is run in headless mode.
            status_callback: Optional callback function to handle status updates.
            replay_events: A list of logs to replay.
        """
        self.id = sid or event_stream.sid
        self.user_id = user_id
        self.file_store = file_store
        self.agent = agent
        self.headless_mode = headless_mode
        self.is_delegate = is_delegate
        self.conversation_stats = conversation_stats

        # the event stream must be set before maybe subscribing to it
        self.event_stream = event_stream

        # subscribe to the event stream if this is not a delegate
        if not self.is_delegate:
            self.event_stream.subscribe(
                EventStreamSubscriber.AGENT_CONTROLLER, self.on_event, self.id
            )

        self.state_tracker = StateTracker(sid, file_store, user_id)

        # state from the previous session, state from a parent agent, or a fresh state
        self.set_initial_state(
            state=initial_state,
            conversation_stats=conversation_stats,
            max_iterations=iteration_delta,
            max_budget_per_task=budget_per_task_delta,
            confirmation_mode=confirmation_mode,
        )

        self.state = self.state_tracker.state  # TODO: share between manager and controller for backward compatability; we should ideally move all state related logic to the state manager

        self.agent_to_llm_config = agent_to_llm_config if agent_to_llm_config else {}
        self.agent_configs = agent_configs if agent_configs else {}
        self.security_analyzer = security_analyzer

        # Underwood Bounded Mode: Initialize immutable permission context and audit tracking
        if getattr(self.agent.config, 'bounded_mode', False):
            # Provably equivalent deny set: all exported actions minus the allowed ones
            from openhands.events.action import __all__ as exported_action_names

            allowed_action_names = {
                'CmdRunAction',
                'FileReadAction',
                'FileWriteAction',
                'FileEditAction',
                'MessageAction',
                'AgentFinishAction',
                'AgentRejectAction',
                'ChangeAgentStateAction',
                'NullAction',
                'LoopRecoveryAction',
                'SystemMessageAction',
                'CondensationAction',
                'CondensationRequestAction',
            }

            deny_names = {
                name
                for name in exported_action_names
                if name not in allowed_action_names and name.endswith('Action')
            }
            # Add Action itself if exported and not allowed
            if 'Action' in exported_action_names and 'Action' not in allowed_action_names:
                deny_names.add('Action')

            self._permission_context = ToolPermissionContext(deny_names=deny_names)
            self._heartbeat_presence = {
                'step_started': False,
                'step_completed': False,
                'termination_triggered': False,
                'step_delta': False
            }
        else:
            self._permission_context = None
            self._heartbeat_presence = {}

        self._pending_action: Action | None = None
        self._task_sequence: list[str] = []
        self._task_index: int = 0
        self._executed_path: list[int] = [self._task_index]
        self._sequence_snapshot: dict[str, Any] | None = None
        self._sequence_replay_boundaries: list[dict[str, Any]] = []
        self._pre_execution_gate_completed: bool = False
        self._pre_execution_gate_reason: str | None = None
        self._task_graph: dict[str, Any] = {
            'nodes': [],
            'edges': []
        }

        self._initial_max_iterations = iteration_delta
        self._initial_max_budget_per_task = budget_per_task_delta

        # Phase 17C: Internal Enforced Parameter State
        self._enforced_max_iterations = iteration_delta
        self._enforced_bounded_mode = getattr(self.agent.config, 'bounded_mode', False)
        self._enforcement_status = {}

        # stuck helper
        self._stuck_detector = StuckDetector(self.state)
        self.status_callback = status_callback

        # replay-related
        self._replay_manager = ReplayManager(replay_events)

        self.confirmation_mode = confirmation_mode

        # security analyzer for direct access
        self.security_analyzer = security_analyzer

        # Add the system message to the event stream
        self._add_system_message()

    async def _handle_security_analyzer(self, action: Action) -> None:
        """Handle security risk analysis for an action.

        If a security analyzer is configured, use it to analyze the action.
        If no security analyzer is configured, set the risk to HIGH (fail-safe approach).

        Args:
            action: The action to analyze for security risks.
        """
        if self.security_analyzer:
            try:
                if (
                    hasattr(action, 'security_risk')
                    and action.security_risk is not None
                ):
                    logger.debug(
                        f'Original security risk for {action}: {action.security_risk})'
                    )
                if hasattr(action, 'security_risk'):
                    action.security_risk = await self.security_analyzer.security_risk(
                        action
                    )
                    logger.debug(
                        f'[Security Analyzer: {self.security_analyzer.__class__}] Override security risk for action {action}: {action.security_risk}'
                    )
            except Exception as e:
                logger.warning(
                    f'Failed to analyze security risk for action {action}: {e}'
                )
                if hasattr(action, 'security_risk'):
                    action.security_risk = ActionSecurityRisk.UNKNOWN
        else:
            # When no security analyzer is configured, treat all actions as UNKNOWN risk
            # This is a fail-safe approach that ensures confirmation is required
            logger.debug(
                f'No security analyzer configured, setting UNKNOWN risk for action: {action}'
            )
            if hasattr(action, 'security_risk'):
                action.security_risk = ActionSecurityRisk.UNKNOWN

    def _add_system_message(self):
        for event in self.event_stream.search_events(start_id=self.state.start_id):
            if isinstance(event, MessageAction) and event.source == EventSource.USER:
                # FIXME: Remove this after 6/1/2025
                # Do not try to add a system message if we first run into
                # a user message -- this means the eventstream exits before
                # SystemMessageAction is introduced.
                # We expect *agent* to handle this case gracefully.
                return

            if isinstance(event, SystemMessageAction):
                # Do not try to add the system message if it already exists
                return

        # Reset Underwood bounded mode flags per task
        self._validation_triggered = False
        self._validation_completed = False

        # FORCED TEST OVERRIDE
        self.agent.config.bounded_mode = True
        self.agent.config.bounded_validation_command = 'test -f test.txt'

        # Add the system message to the event stream
        # This should be done for all agents, including delegates
        system_message = self.agent.get_system_message()

        if system_message and system_message.content:
            preview = (
                system_message.content[:50] + '...'
                if len(system_message.content) > 50
                else system_message.content
            )
            logger.debug(f'System message: {preview}')
            self.event_stream.add_event(system_message, EventSource.AGENT)

    async def close(self, set_stop_state: bool = True) -> None:
        """Closes the agent controller, canceling any ongoing tasks and unsubscribing from the event stream.

        Note that it's fairly important that this closes properly, otherwise the state is incomplete.
        """
        if set_stop_state:
            await self.set_agent_state_to(AgentState.STOPPED)

        self.state_tracker.close(self.event_stream)

        # unsubscribe from the event stream
        # only the root parent controller subscribes to the event stream
        if not self.is_delegate:
            self.event_stream.unsubscribe(
                EventStreamSubscriber.AGENT_CONTROLLER, self.id
            )
        self._closed = True

    def log(
        self,
        level: str,
        message: str,
        extra: dict | None = None,
        exc_info: bool = False,
    ) -> None:
        """Logs a message to the agent controller's logger.

        Args:
            level (str): The logging level to use (e.g., 'info', 'debug', 'error').
            message (str): The message to log.
            extra (dict | None, optional): Additional fields to log. Includes session_id by default.
            exc_info (bool, optional): Whether to include exception info. Defaults to False.
        """
        message = f'[Agent Controller {self.id}] {message}'
        if extra is None:
            extra = {}
        extra_merged = {'session_id': self.id, **extra}
        getattr(logger, level)(
            message, extra=extra_merged, exc_info=exc_info, stacklevel=2
        )

    async def _react_to_exception(
        self,
        e: Exception,
    ) -> None:
        """React to an exception by setting the agent state to error and sending a status message."""
        # Store the error reason before setting the agent state
        self.state.last_error = f'{type(e).__name__}: {str(e)}'

        if self.status_callback is not None:
            runtime_status = RuntimeStatus.ERROR
            if isinstance(e, AuthenticationError):
                runtime_status = RuntimeStatus.ERROR_LLM_AUTHENTICATION
                self.state.last_error = runtime_status.value
            elif isinstance(
                e,
                (
                    ServiceUnavailableError,
                    APIConnectionError,
                    APIError,
                ),
            ):
                runtime_status = RuntimeStatus.ERROR_LLM_SERVICE_UNAVAILABLE
                self.state.last_error = runtime_status.value
            elif isinstance(e, InternalServerError):
                runtime_status = RuntimeStatus.ERROR_LLM_INTERNAL_SERVER_ERROR
                self.state.last_error = runtime_status.value
            elif isinstance(e, BadRequestError) and 'ExceededBudget' in str(e):
                runtime_status = RuntimeStatus.ERROR_LLM_OUT_OF_CREDITS
                self.state.last_error = runtime_status.value
            elif isinstance(e, ContentPolicyViolationError) or (
                isinstance(e, BadRequestError)
                and 'ContentPolicyViolationError' in str(e)
            ):
                runtime_status = RuntimeStatus.ERROR_LLM_CONTENT_POLICY_VIOLATION
                self.state.last_error = runtime_status.value
            elif isinstance(e, RateLimitError):
                # Check if this is the final retry attempt
                if (
                    hasattr(e, 'retry_attempt')
                    and hasattr(e, 'max_retries')
                    and e.retry_attempt >= e.max_retries
                ):
                    # All retries exhausted, set to ERROR state with a special message
                    self.state.last_error = (
                        RuntimeStatus.AGENT_RATE_LIMITED_STOPPED_MESSAGE.value
                    )
                    await self.set_agent_state_to(AgentState.ERROR)
                else:
                    # Still retrying, set to RATE_LIMITED state
                    await self.set_agent_state_to(AgentState.RATE_LIMITED)
                return
            self.status_callback('error', runtime_status, self.state.last_error)

        # Set the agent state to ERROR after storing the reason
        if self.state.stop_reason is None:
            if 'maximum budget' in str(e).lower() or 'ExceededBudget' in str(e):
                self.state.stop_reason = 'budget_exceeded'
            else:
                self.state.stop_reason = 'runtime_error'
        
        # 🚨 UNDERWOOD LIFECYCLE: termination_triggered 🚨
        if getattr(self.agent.config, 'bounded_mode', False) and self.state.get_local_step() >= 0:
            self._heartbeat_presence['termination_triggered'] = True
            payload = json.dumps({
                'stop_reason': self.state.stop_reason,
                'task_index': self._task_index
            })
            self.event_stream.add_event(
                NullObservation(content=f'[LIFECYCLE:termination_triggered] {payload}'),
                EventSource.AGENT
            )
            
            # 🚨 UNDERWOOD AUDIT (7C) 🚨
            if not self.state.outputs:
                self.state.outputs = {
                    'status': 'error',
                    'message': str(e),
                    'stop_reason': self.state.stop_reason
                }
            audit = self._build_bounded_audit_payload()
            if audit:
                self._emit_terminal_audit_analytics(audit)
                self.state.outputs.update(audit)

        await self.set_agent_state_to(AgentState.ERROR)

    def step(self) -> None:
        asyncio.create_task(self._step_with_exception_handling())

    async def _step_with_exception_handling(self) -> None:
        try:
            await self._step()
        except Exception as e:
            self.log(
                'error',
                f'Error while running the agent (session ID: {self.id}): {e}',
                exc_info=True,
            )
            reported = RuntimeError(
                f'There was an unexpected error while running the agent: {e.__class__.__name__}. You can refresh the page or ask the agent to try again.'
            )
            if (
                isinstance(e, Timeout)
                or isinstance(e, APIError)
                or isinstance(e, BadRequestError)
                or isinstance(e, NotFoundError)
                or isinstance(e, InternalServerError)
                or isinstance(e, AuthenticationError)
                or isinstance(e, RateLimitError)
                or isinstance(e, ContentPolicyViolationError)
                or isinstance(e, LLMContextWindowExceedError)
            ):
                reported = e
            else:
                self.log(
                    'warning',
                    f'Unknown exception type while running the agent: {type(e).__name__}.',
                )
            await self._react_to_exception(reported)

    def should_step(self, event: Event) -> bool:
        """Whether the agent should take a step based on an event.

        In general, the agent should take a step if it receives a message from the user,
        or observes something in the environment (after acting).
        """
        # 🚨 UNDERWOOD ABSOLUTE STOP 🚨
        if getattr(self.agent.config, 'bounded_mode', False) and getattr(self, '_validation_completed', False):
            return False

        # it might be the delegate's day in the sun
        if self.delegate is not None:
            return False

        if isinstance(event, Action):
            if isinstance(event, MessageAction) and event.source == EventSource.USER:
                return True
            if (
                isinstance(event, MessageAction)
                and self.get_agent_state() != AgentState.AWAITING_USER_INPUT
            ):
                # TODO: this is fragile, but how else to check if eligible?
                return True
            if isinstance(event, AgentDelegateAction):
                return True
            if isinstance(event, CondensationAction):
                return True
            if isinstance(event, CondensationRequestAction):
                return True
            return False
        if isinstance(event, Observation):
            if (
                isinstance(event, NullObservation)
                and event.cause is not None
                and event.cause
                > 0  # NullObservation has cause > 0 (RecallAction), not 0 (user message)
            ):
                return True
            if isinstance(event, AgentStateChangedObservation) or isinstance(
                event, NullObservation
            ):
                return False

            # Underwood: Do not step if the agent is already in a terminal state
            if self.get_agent_state() in (
                AgentState.FINISHED,
                AgentState.ERROR,
                AgentState.REJECTED,
            ):
                return False

            return True
        return False

    def on_event(self, event: Event) -> None:
        """Callback from the event stream. Notifies the controller of incoming events.

        Args:
            event (Event): The incoming event to process.
        """
        # If we have a delegate that is not finished or errored, forward events to it
        if self.delegate is not None:
            delegate_state = self.delegate.get_agent_state()
            if (
                delegate_state
                not in (
                    AgentState.FINISHED,
                    AgentState.ERROR,
                    AgentState.REJECTED,
                )
                or 'RuntimeError: Agent reached maximum iteration.'
                in self.delegate.state.last_error
                or 'RuntimeError:Agent reached maximum budget for conversation'
                in self.delegate.state.last_error
            ):
                # Forward the event to delegate and skip parent processing
                asyncio.get_event_loop().run_until_complete(
                    self.delegate._on_event(event)
                )
                return
            else:
                # delegate is done or errored, so end it
                self.end_delegate()
                return

        # continue parent processing only if there's no active delegate
        asyncio.get_event_loop().run_until_complete(self._on_event(event))

    async def _on_event(self, event: Event) -> None:
        if hasattr(event, 'hidden') and event.hidden:
            return

        self.state_tracker.add_history(event)

        if isinstance(event, Action):
            await self._handle_action(event)
        elif isinstance(event, Observation):
            await self._handle_observation(event)

        should_step = self.should_step(event)
        if should_step:
            self.log(
                'debug',
                f'Stepping agent after event: {type(event).__name__}',
                extra={'msg_type': 'STEPPING_AGENT'},
            )
            await self._step_with_exception_handling()
        elif isinstance(event, MessageAction) and event.source == EventSource.USER:
            # If we received a user message but aren't stepping, log why
            self.log(
                'warning',
                f'Not stepping agent after user message. Current state: {self.get_agent_state()}',
                extra={'msg_type': 'NOT_STEPPING_AFTER_USER_MESSAGE'},
            )

    async def _handle_action(self, action: Action) -> None:
        """Handles an Action from the agent or delegate."""
        if isinstance(action, ChangeAgentStateAction):
            await self.set_agent_state_to(action.agent_state)  # type: ignore
        elif isinstance(action, MessageAction):
            await self._handle_message_action(action)
        elif isinstance(action, AgentDelegateAction):
            await self.start_delegate(action)
            assert self.delegate is not None
            # Post a MessageAction with the task for the delegate
            if 'task' in action.inputs:
                self.event_stream.add_event(
                    MessageAction(content='TASK: ' + action.inputs['task']),
                    EventSource.USER,
                )
                await self.delegate.set_agent_state_to(AgentState.RUNNING)
            return

        elif isinstance(action, AgentFinishAction):
            self.state.outputs = action.outputs
            if self.state.stop_reason is None:
                self.state.stop_reason = 'task_completed'
            await self.set_agent_state_to(AgentState.FINISHED)
        elif isinstance(action, AgentRejectAction):
            self.state.outputs = action.outputs
            if self.state.stop_reason is None:
                self.state.stop_reason = 'task_completed'
            await self.set_agent_state_to(AgentState.REJECTED)
        elif isinstance(action, LoopRecoveryAction):
            await self._handle_loop_recovery_action(action)

    async def _handle_observation(self, observation: Observation) -> None:
        """Handles observation from the event stream.
        """
        # Underwood Bounded Mode: Handle termination on validation result

        # Underwood Bounded Mode: Handle termination on validation result
        if self.agent.config.bounded_mode:
            self.log('info', f'UNDERWOOD DEBUG: Handling observation: {type(observation).__name__}')
            self.log('info', f'UNDERWOOD DEBUG: _validation_triggered = {self._validation_triggered}')

        if (
            self.agent.config.bounded_mode
            and self._validation_triggered
            and isinstance(observation, CmdOutputObservation)
        ):
            self.log('info', f'UNDERWOOD DEBUG: Validation observation received with exit_code {observation.exit_code}')
            
            # SET COMPLETION FLAG BEFORE STATE CHANGE
            self._validation_completed = True
            
            if observation.exit_code == 0:
                self.log('info', 'UNDERWOOD: validation result = success')
                if self.state.stop_reason is None:
                    self.state.stop_reason = 'validation_succeeded'
                self.state.outputs = {'status': 'success', 'message': 'Validation passed', 'stop_reason': self.state.stop_reason}
                await self.set_agent_state_to(AgentState.FINISHED)
                # 🚨 UNDERWOOD LIFECYCLE: termination_triggered 🚨
                if getattr(self.agent.config, 'bounded_mode', False) and self.state.get_local_step() >= 0:
                    self._heartbeat_presence['termination_triggered'] = True
                    payload = json.dumps({
                        'stop_reason': self.state.stop_reason,
                        'task_index': self._task_index
                    })
                    self.event_stream.add_event(
                        NullObservation(content=f'[LIFECYCLE:termination_triggered] {payload}'),
                        EventSource.AGENT
                    )
                
                # 🚨 UNDERWOOD AUDIT (7C) 🚨
                audit = self._build_bounded_audit_payload()
                if audit:
                    self._emit_terminal_audit_analytics(audit)
                    self.state.outputs.update(audit)

                self.event_stream.add_event(
                    AgentFinishAction(outputs=self.state.outputs),
                    EventSource.AGENT
                )
            else:
                self.log('info', 'UNDERWOOD: validation result = failure')
                if self.state.stop_reason is None:
                    self.state.stop_reason = 'validation_failed'
                self.state.outputs = {'status': 'failure', 'message': f'Validation failed with exit code {observation.exit_code}', 'stop_reason': self.state.stop_reason}
                
                # 🚨 UNDERWOOD LIFECYCLE: termination_triggered 🚨
                if getattr(self.agent.config, 'bounded_mode', False) and self.state.get_local_step() >= 0:
                    self._heartbeat_presence['termination_triggered'] = True
                    payload = json.dumps({
                        'stop_reason': self.state.stop_reason,
                        'task_index': self._task_index
                    })
                    self.event_stream.add_event(
                        NullObservation(content=f'[LIFECYCLE:termination_triggered] {payload}'),
                        EventSource.AGENT
                    )
                
                # 🚨 UNDERWOOD AUDIT (7C) 🚨
                audit = self._build_bounded_audit_payload()
                if audit:
                    self._emit_terminal_audit_analytics(audit)
                    self.state.outputs.update(audit)

                await self.set_agent_state_to(AgentState.ERROR)
                self.event_stream.add_event(
                    AgentFinishAction(outputs=self.state.outputs),
                    EventSource.AGENT
                )
            return  # Stop processing further observation logic

        observation_to_print = copy.deepcopy(observation)
        if len(observation_to_print.content) > self.agent.llm.config.max_message_chars:
            observation_to_print.content = truncate_content(
                observation_to_print.content, self.agent.llm.config.max_message_chars
            )
        # Use info level if LOG_ALL_EVENTS is set
        log_level = 'info' if os.getenv('LOG_ALL_EVENTS') in ('true', '1') else 'debug'
        self.log(
            log_level, str(observation_to_print), extra={'msg_type': 'OBSERVATION'}
        )

        # this happens for runnable actions and microagent actions
        if self._pending_action and self._pending_action.id == observation.cause:
            if self.state.agent_state == AgentState.AWAITING_USER_CONFIRMATION:
                return

            self._pending_action = None

            if self.state.agent_state == AgentState.USER_CONFIRMED:
                await self.set_agent_state_to(AgentState.RUNNING)
            if self.state.agent_state == AgentState.USER_REJECTED:
                await self.set_agent_state_to(AgentState.AWAITING_USER_INPUT)
            return


    async def _handle_message_action(self, action: MessageAction) -> None:
        """Handles message actions from the event stream.

        Args:
            action (MessageAction): The message action to handle.
        """
        if action.source == EventSource.USER:
            # Use info level if LOG_ALL_EVENTS is set
            log_level = (
                'info' if os.getenv('LOG_ALL_EVENTS') in ('true', '1') else 'debug'
            )
            self.log(
                log_level,
                str(action),
                extra={'msg_type': 'ACTION', 'event_source': EventSource.USER},
            )

            # if this is the first user message for this agent, matters for the microagent info type
            first_user_message = self._first_user_message()
            is_first_user_message = (
                action.id == first_user_message.id if first_user_message else False
            )
            recall_type = (
                RecallType.WORKSPACE_CONTEXT
                if is_first_user_message
                else RecallType.KNOWLEDGE
            )

            recall_action = RecallAction(query=action.content, recall_type=recall_type)
            self._pending_action = recall_action
            # this is source=USER because the user message is the trigger for the microagent retrieval
            self.event_stream.add_event(recall_action, EventSource.USER)

            if self.get_agent_state() != AgentState.RUNNING:
                await self.set_agent_state_to(AgentState.RUNNING)

        elif action.source == EventSource.AGENT:
            # If the agent is waiting for a response, set the appropriate state
            if action.wait_for_response:
                await self.set_agent_state_to(AgentState.AWAITING_USER_INPUT)

    async def _handle_loop_recovery_action(self, action: LoopRecoveryAction) -> None:
        # Check if this is a loop recovery option
        if self._stuck_detector.stuck_analysis:
            option = action.option

            # Handle the loop recovery option
            if option == 1:
                # Option 1: Restart from before loop
                await self._perform_loop_recovery(self._stuck_detector.stuck_analysis)
            elif option == 2:
                # Option 2: Restart with last user message
                await self._restart_with_last_user_message(
                    self._stuck_detector.stuck_analysis
                )
            elif option == 3:
                # Option 3: Stop agent completely
                await self.set_agent_state_to(AgentState.STOPPED)
            return

    def _reset(self) -> None:
        """Resets the agent controller."""
        # Runnable actions need an Observation
        # make sure there is an Observation with the tool call metadata to be recognized by the agent
        # otherwise the pending action is found in history, but it's incomplete without an obs with tool result
        if self._pending_action and hasattr(self._pending_action, 'tool_call_metadata'):
            # find out if there already is an observation with the same tool call metadata
            found_observation = False
            for event in self.state.history:
                if (
                    isinstance(event, Observation)
                    and event.tool_call_metadata
                    == self._pending_action.tool_call_metadata
                ):
                    found_observation = True
                    break

            # make a new ErrorObservation with the tool call metadata
            if not found_observation:
                # Use different messages and IDs based on whether the agent was stopped by user or due to error
                if self.state.agent_state == AgentState.STOPPED:
                    error_content = ERROR_ACTION_NOT_EXECUTED_STOPPED
                    error_id = ERROR_ACTION_NOT_EXECUTED_STOPPED_ID
                else:  # AgentState.ERROR
                    error_content = ERROR_ACTION_NOT_EXECUTED_ERROR
                    error_id = ERROR_ACTION_NOT_EXECUTED_ERROR_ID

                obs = ErrorObservation(
                    content=error_content,
                    error_id=error_id,
                )
                obs.tool_call_metadata = self._pending_action.tool_call_metadata
                obs._cause = self._pending_action.id  # type: ignore[attr-defined]
                self.event_stream.add_event(obs, EventSource.AGENT)

        # NOTE: RecallActions don't need an ErrorObservation upon reset, as long as they have no tool calls

        # reset the pending action, this will be called when the agent is STOPPED or ERROR
        self._pending_action = None
        self.agent.reset()

    async def set_agent_state_to(self, new_state: AgentState) -> None:
        """Updates the agent's state and handles side effects. Can emit events to the event stream.

        Args:
            new_state (AgentState): The new state to set for the agent.
        """
        self.log(
            'info',
            f'Setting agent({self.agent.name}) state from {self.state.agent_state} to {new_state}',
        )

        if new_state == self.state.agent_state:
            return

        # Store old state for control limits check
        old_state = self.state.agent_state

        # Update agent state BEFORE calling _reset() so _reset() sees the correct state
        self.state.agent_state = new_state

        if new_state in (AgentState.STOPPED, AgentState.ERROR):
            self._reset()

        # User is allowing to check control limits and expand them if applicable
        if old_state == AgentState.ERROR and new_state == AgentState.RUNNING:
            self.state_tracker.maybe_increase_control_flags_limits(self.headless_mode)

        if self._pending_action is not None and (
            new_state in (AgentState.USER_CONFIRMED, AgentState.USER_REJECTED)
        ):
            if hasattr(self._pending_action, 'thought'):
                self._pending_action.thought = ''  # type: ignore[union-attr]
            if new_state == AgentState.USER_CONFIRMED:
                confirmation_state = ActionConfirmationStatus.CONFIRMED
            else:
                confirmation_state = ActionConfirmationStatus.REJECTED
            self._pending_action.confirmation_state = confirmation_state  # type: ignore[attr-defined]
            self._pending_action._id = None  # type: ignore[attr-defined]
            self.event_stream.add_event(self._pending_action, EventSource.AGENT)

        # Create observation with reason field if it's an error state
        reason = ''
        if new_state == AgentState.ERROR:
            reason = self.state.last_error

        self.event_stream.add_event(
            AgentStateChangedObservation('', self.state.agent_state, reason),
            EventSource.ENVIRONMENT,
        )

        # Save state whenever agent state changes to ensure we don't lose state
        # in case of crashes or unexpected circumstances
        self.save_state()

    def get_agent_state(self) -> AgentState:
        """Returns the current state of the agent.

        Returns:
            AgentState: The current state of the agent.
        """
        return self.state.agent_state

    async def start_delegate(self, action: AgentDelegateAction) -> None:
        """Start a delegate agent to handle a subtask.

        OpenHands is a multi-agentic system. A `task` is a conversation between
        OpenHands (the whole system) and the user, which might involve one or more inputs
        from the user. It starts with an initial input (typically a task statement) from
        the user, and ends with either an `AgentFinishAction` initiated by the agent, a
        stop initiated by the user, or an error.

        A `subtask` is a conversation between an agent and the user, or another agent. If a `task`
        is conducted by a single agent, then it's also a `subtask`. Otherwise, a `task` consists of
        multiple `subtasks`, each executed by one agent.

        Args:
            action (AgentDelegateAction): The action containing information about the delegate agent to start.
        """
        agent_cls: type[Agent] = Agent.get_cls(action.agent)
        agent_config = self.agent_configs.get(action.agent, self.agent.config)
        # Make sure metrics are shared between parent and child for global accumulation
        delegate_agent = agent_cls(
            config=agent_config, llm_registry=self.agent.llm_registry
        )

        # Take a snapshot of the current metrics before starting the delegate
        state = State(
            session_id=self.id.removesuffix('-delegate'),
            user_id=self.user_id,
            inputs=action.inputs or {},
            iteration_flag=self.state.iteration_flag,
            budget_flag=self.state.budget_flag,
            delegate_level=self.state.delegate_level + 1,
            # global metrics should be shared between parent and child
            metrics=self.state.metrics,
            # start on top of the stream
            start_id=self.event_stream.get_latest_event_id() + 1,
            parent_metrics_snapshot=self.state_tracker.get_metrics_snapshot(),
            parent_iteration=self.state.iteration_flag.current_value,
        )
        self.log(
            'debug',
            f'start delegate, creating agent {delegate_agent.name}',
        )

        # Create the delegate with is_delegate=True so it does NOT subscribe directly
        self.delegate = AgentController(
            sid=self.id + '-delegate',
            file_store=self.file_store,
            user_id=self.user_id,
            agent=delegate_agent,
            event_stream=self.event_stream,
            conversation_stats=self.conversation_stats,
            iteration_delta=self._initial_max_iterations,
            budget_per_task_delta=self._initial_max_budget_per_task,
            agent_to_llm_config=self.agent_to_llm_config,
            agent_configs=self.agent_configs,
            initial_state=state,
            is_delegate=True,
            headless_mode=self.headless_mode,
            security_analyzer=self.security_analyzer,
        )

    def end_delegate(self) -> None:
        """Ends the currently active delegate (e.g., if it is finished or errored).

        so that this controller can resume normal operation.
        """
        if self.delegate is None:
            return

        delegate_state = self.delegate.get_agent_state()

        # update iteration that is shared across agents
        self.state.iteration_flag.current_value = (
            self.delegate.state.iteration_flag.current_value
        )

        # Calculate delegate-specific metrics before closing the delegate
        delegate_metrics = self.state.get_local_metrics()
        logger.info(f'Local metrics for delegate: {delegate_metrics}')

        # close the delegate controller before adding new events
        asyncio.get_event_loop().run_until_complete(self.delegate.close())

        if delegate_state in (AgentState.FINISHED, AgentState.REJECTED):
            # retrieve delegate result
            delegate_outputs = (
                self.delegate.state.outputs if self.delegate.state else {}
            )

            # prepare delegate result observation
            # TODO: replace this with AI-generated summary (#2395)
            # Filter out metrics from the formatted output to avoid clutter
            display_outputs = {
                k: v for k, v in delegate_outputs.items() if k != 'metrics'
            }
            formatted_output = ', '.join(
                f'{key}: {value}' for key, value in display_outputs.items()
            )
            content = (
                f'{self.delegate.agent.name} finishes task with {formatted_output}'
            )
        else:
            # delegate state is ERROR
            # emit AgentDelegateObservation with error content
            delegate_outputs = (
                self.delegate.state.outputs if self.delegate.state else {}
            )
            content = (
                f'{self.delegate.agent.name} encountered an error during execution.'
            )

        content = f'Delegated agent finished with result:\n\n{content}'

        # emit the delegate result observation
        obs = AgentDelegateObservation(outputs=delegate_outputs, content=content)

        # associate the delegate action with the initiating tool call
        for event in reversed(self.state.history):
            if isinstance(event, AgentDelegateAction):
                delegate_action = event
                obs.tool_call_metadata = delegate_action.tool_call_metadata
                break

        self.event_stream.add_event(obs, EventSource.AGENT)

        # unset delegate so parent can resume normal handling
        self.delegate = None

    async def _step(self) -> None:
        """Executes a single step of the parent or delegate agent. Detects stuck agents and limits on the number of iterations and the task budget."""
        # 🚨 UNDERWOOD SNAPSHOT ISOLATION 🚨
        # Create a stable snapshot of the controller context for the duration of this step.
        step_config = self.agent.config
        is_bounded = getattr(step_config, 'bounded_mode', False)

        # 🚨 UNDERWOOD SEQUENCE SNAPSHOT CAPTURE (10A) 🚨
        if self._sequence_snapshot is None:
            self._capture_sequence_snapshot()

        # 🚨 UNDERWOOD PRE-EXECUTION DECISION GATE (12B) 🚨
        if is_bounded and not self._pre_execution_gate_completed:
            await self._run_pre_execution_gate()
            if self.state.stop_reason == 'gate_refusal':
                return

        # 🚨 UNDERWOOD SEQUENCE ACTIVATION CONTROL POINT (9A/9B/9C) 🚨
        if is_bounded and self.state.stop_reason:
            if self._should_activate_next_task():
                # 🚨 UNDERWOOD SEQUENCE ITERATION GUARD (9C) 🚨
                if self._sequence_iterations_exceeded():
                    self.log('info', 'UNDERWOOD: sequence termination triggered by global iteration guard')
                    return

                await self._activate_next_task()
                return

            # 🚨 UNDERWOOD FAIL-FAST ENFORCEMENT (9B) 🚨
            if self._sequence_should_terminate():
                self.log('info', f'UNDERWOOD: sequence termination triggered by fail-fast policy (reason: {self.state.stop_reason})')
                # Fall through to standard terminal state handling

        validation_completed = getattr(self, '_validation_completed', False)
        permission_context = self._permission_context

        # 🚨 UNDERWOOD SNAPSHOT (7B) 🚨
        if is_bounded:
            start_snapshot = {
                'step': self.state.get_local_step(),
                'is_bounded': is_bounded,
                'validation_triggered': getattr(self, '_validation_triggered', False),
                'validation_completed': getattr(self, '_validation_completed', False),
                'stop_reason': self.state.stop_reason,
            }

        # 🚨 UNDERWOOD LIFECYCLE: step_started 🚨
        if is_bounded and self.state.get_local_step() >= 0:
            self._heartbeat_presence['step_started'] = True
            payload = json.dumps({
                'step': self.state.get_local_step(),
                'is_bounded': is_bounded,
                'task_index': self._task_index
            })
            self.event_stream.add_event(
                NullObservation(content=f'[LIFECYCLE:step_started] {payload}'),
                EventSource.AGENT
            )
        if is_bounded and validation_completed:
            self._emit_step_delta(start_snapshot, is_bounded)
            return

        # Underwood Bounded Mode: Hard Pre-Execution Turn Ceiling
        if is_bounded:
            local_step = self.state.get_local_step()
            if local_step >= 10:
                self.log('info', 'UNDERWOOD: hard pre-execution stop triggered (max steps reached)')
                if self.state.stop_reason is None:
                    self.state.stop_reason = 'max_turns_reached'
                self.state.outputs = {
                    'status': 'failure',
                    'message': 'bounded_mode_max_steps_exceeded',
                    'stop_reason': self.state.stop_reason,
                }
                await self.set_agent_state_to(AgentState.ERROR)
                # 🚨 UNDERWOOD LIFECYCLE: termination_triggered 🚨
                if is_bounded and self.state.get_local_step() >= 0:
                    self._heartbeat_presence['termination_triggered'] = True
                    payload = json.dumps({
                        'stop_reason': self.state.stop_reason,
                        'task_index': self._task_index
                    })
                    self.event_stream.add_event(
                        NullObservation(content=f'[LIFECYCLE:termination_triggered] {payload}'),
                        EventSource.AGENT
                    )
                
                # 🚨 UNDERWOOD AUDIT (7C) 🚨
                audit = self._build_bounded_audit_payload()
                if audit:
                    self._emit_terminal_audit_analytics(audit)
                    self.state.outputs.update(audit)

                self.event_stream.add_event(
                    AgentFinishAction(outputs=self.state.outputs),
                    EventSource.AGENT
                )
                self._emit_step_delta(start_snapshot, is_bounded)
                return

        if self.get_agent_state() != AgentState.RUNNING:
            self.log(
                'debug',
                f'Agent not stepping because state is {self.get_agent_state()} (not RUNNING)',
                extra={'msg_type': 'STEP_BLOCKED_STATE'},
            )
            if is_bounded:
                self._emit_step_delta(start_snapshot, is_bounded)
            return

        if self._pending_action:
            action_id = getattr(self._pending_action, 'id', 'unknown')
            action_type = type(self._pending_action).__name__
            self.log(
                'debug',
                f'Agent not stepping because of pending action: {action_type} (id={action_id})',
                extra={'msg_type': 'STEP_BLOCKED_PENDING_ACTION'},
            )
            if is_bounded:
                self._emit_step_delta(start_snapshot, is_bounded)
            return

        self.log(
            'debug',
            f'LEVEL {self.state.delegate_level} LOCAL STEP {self.state.get_local_step()} GLOBAL STEP {self.state.iteration_flag.current_value}',
            extra={'msg_type': 'STEP'},
        )

        # Synchronize spend across all llm services with the budget flag
        self.state_tracker.sync_budget_flag_with_metrics()
        if step_config.enable_stuck_detection and self._is_stuck():
            await self._react_to_exception(
                AgentStuckInLoopError('Agent got stuck in a loop')
            )
            if is_bounded:
                self._emit_step_delta(start_snapshot, is_bounded)
            return

        try:
            self.state_tracker.run_control_flags()
        except Exception as e:
            logger.warning('Control flag limits hit')
            await self._react_to_exception(e)
            if is_bounded:
                self._emit_step_delta(start_snapshot, is_bounded)
            return

        # Underwood Bounded Mode: Block execution after validation is triggered
        if is_bounded and self._validation_triggered:
            self.log('info', 'UNDERWOOD: blocking execution post-validation trigger')
            self._emit_step_delta(start_snapshot, is_bounded)
            return

        action: Action = NullAction()

        if self._replay_manager.should_replay():
            # in replay mode, we don't let the agent to proceed
            # instead, we replay the action from the replay trajectory
            action = self._replay_manager.step()
        else:
            try:
                action = self.agent.step(self.state)
                if action is None:
                    raise LLMNoActionError('No action was returned')
                action._source = EventSource.AGENT  # type: ignore [attr-defined]
            except (
                LLMMalformedActionError,
                LLMNoActionError,
                LLMResponseError,
                FunctionCallValidationError,
                FunctionCallNotExistsError,
            ) as e:
                self.event_stream.add_event(
                    ErrorObservation(
                        content=str(e),
                    ),
                    EventSource.AGENT,
                )
                if is_bounded:
                    self._emit_step_delta(start_snapshot, is_bounded)
                return
            except (ContextWindowExceededError, BadRequestError, OpenAIError) as e:
                # FIXME: this is a hack until a litellm fix is confirmed
                # Check if this is a nested context window error
                # We have to rely on string-matching because LiteLLM doesn't consistently
                # wrap the failure in a ContextWindowExceededError
                error_str = str(e).lower()
                if (
                    'contextwindowexceedederror' in error_str
                    or 'prompt is too long' in error_str
                    or 'input length and `max_tokens` exceed context limit' in error_str
                    or 'please reduce the length of' in error_str
                    or 'the request exceeds the available context size' in error_str
                    or 'context length exceeded' in error_str
                    # For OpenRouter context window errors
                    or (
                        'sambanovaexception' in error_str
                        and 'maximum context length' in error_str
                    )
                    # For SambaNova context window errors - only match when both patterns are present
                    or isinstance(e, ContextWindowExceededError)
                ):
                    if step_config.enable_history_truncation:
                        self.event_stream.add_event(
                            CondensationRequestAction(), EventSource.AGENT
                        )
                        if is_bounded:
                            self._emit_step_delta(start_snapshot, is_bounded)
                        return
                    else:
                        raise LLMContextWindowExceedError()
                # Check if this is a tool call validation error that should be recoverable
                elif (
                    isinstance(e, BadRequestError)
                    and 'tool call validation failed' in error_str
                    and (
                        'missing properties' in error_str
                        or 'missing required' in error_str
                    )
                ):
                    # Handle tool call validation errors from Groq as recoverable errors
                    self.event_stream.add_event(
                        ErrorObservation(
                            content=f'Tool call validation failed: {str(e)}. Please check the tool parameters and try again.',
                        ),
                        EventSource.AGENT,
                    )
                    if is_bounded:
                        self._emit_step_delta(start_snapshot, is_bounded)
                    return
                else:
                    raise e

        # 🚨 UNDERWOOD LIFECYCLE: step_completed 🚨
        if is_bounded and self.state.get_local_step() >= 0:
            self._heartbeat_presence['step_completed'] = True
            payload = json.dumps({
                'action': type(action).__name__ if action else 'None',
                'task_index': self._task_index
            })
            self.event_stream.add_event(
                NullObservation(content=f'[LIFECYCLE:step_completed] {payload}'),
                EventSource.AGENT
            )

        if is_bounded and permission_context:
            if permission_context.blocks(type(action).__name__):
                self.log(
                    'warning',
                    f'UNDERWOOD: Blocked restricted tool: {type(action).__name__}',
                )
                self.event_stream.add_event(
                    ErrorObservation(
                        content=f'Tool {type(action).__name__} is restricted in Bounded Mode. Only Bash and File Editor are allowed.',
                    ),
                    EventSource.AGENT,
                )
                self._emit_step_delta(start_snapshot, is_bounded)
                return

            if isinstance(action, CmdRunAction):
                val_cmd = step_config.bounded_validation_command
                if val_cmd and action.command == val_cmd:
                    self._validation_triggered = True

        if is_bounded and self._validation_triggered:
            self.log('info', 'UNDERWOOD: validation is already triggered, blocking any further steps.')
            self._emit_step_delta(start_snapshot, is_bounded)
            return

        if is_bounded:
            self._emit_step_delta(start_snapshot, is_bounded)

        if action.runnable:
            if self.state.confirmation_mode and (
                type(action) is CmdRunAction
                or type(action) is IPythonRunCellAction
                or type(action) is BrowseInteractiveAction
                or type(action) is BrowseURLAction
                or type(action) is FileEditAction
                or type(action) is FileReadAction
                or type(action) is FileWriteAction
                or type(action) is MCPAction
            ):
                # Handle security risk analysis using the dedicated method
                await self._handle_security_analyzer(action)

                # Check if the action has a security_risk attribute set by the LLM or security analyzer
                security_risk = getattr(
                    action, 'security_risk', ActionSecurityRisk.UNKNOWN
                )

                is_high_security_risk = security_risk == ActionSecurityRisk.HIGH
                is_ask_for_every_action = (
                    security_risk == ActionSecurityRisk.UNKNOWN
                    and not self.security_analyzer
                )

                # If security_risk is HIGH, requires confirmation
                # UNLESS it is CLI which will handle action risks it itself
                if step_config.cli_mode:
                    # TODO(refactor): this is not ideal to have CLI been an exception
                    # We should refactor agent controller to consider this in the future
                    # See issue: https://github.com/OpenHands/OpenHands/issues/10464
                    action.confirmation_state = (  # type: ignore[union-attr]
                        ActionConfirmationStatus.AWAITING_CONFIRMATION
                    )
                # Only HIGH security risk actions require confirmation
                elif (
                    is_high_security_risk or is_ask_for_every_action
                ) and self.confirmation_mode:
                    logger.debug(
                        f'[non-CLI mode] Detected HIGH security risk in action: {action}. Ask for confirmation'
                    )
                    action.confirmation_state = (  # type: ignore[union-attr]
                        ActionConfirmationStatus.AWAITING_CONFIRMATION
                    )
            self._pending_action = action

        if not isinstance(action, NullAction):
            if (
                hasattr(action, 'confirmation_state')
                and action.confirmation_state
                == ActionConfirmationStatus.AWAITING_CONFIRMATION
            ):
                await self.set_agent_state_to(AgentState.AWAITING_USER_CONFIRMATION)

            # Create and log metrics for frontend display
            self._prepare_metrics_for_frontend(action)

            self.event_stream.add_event(action, action._source)  # type: ignore [attr-defined]

        log_level = 'info' if LOG_ALL_EVENTS else 'debug'
        self.log(log_level, str(action), extra={'msg_type': 'ACTION'})

    @property
    def _pending_action(self) -> Action | None:
        """Get the current pending action with time tracking.

        Returns:
            Action | None: The current pending action, or None if there isn't one.
        """
        if self._pending_action_info is None:
            return None

        action, timestamp = self._pending_action_info
        current_time = time.time()
        elapsed_time = current_time - timestamp

        # Log if the pending action has been active for a long time (but don't clear it)
        if elapsed_time > 60.0:  # 1 minute - just for logging purposes
            action_id = getattr(action, 'id', 'unknown')
            action_type = type(action).__name__
            self.log(
                'info',
                f'Pending action active for {elapsed_time:.2f}s: {action_type} (id={action_id})',
                extra={'msg_type': 'PENDING_ACTION_TIMEOUT'},
            )

        return action

    @_pending_action.setter
    def _pending_action(self, action: Action | None) -> None:
        """Set or clear the pending action with timestamp and logging.

        Args:
            action: The action to set as pending, or None to clear.
        """
        if action is None:
            if self._pending_action_info is not None:
                prev_action, timestamp = self._pending_action_info
                action_id = getattr(prev_action, 'id', 'unknown')
                action_type = type(prev_action).__name__
                elapsed_time = time.time() - timestamp
                self.log(
                    'debug',
                    f'Cleared pending action after {elapsed_time:.2f}s: {action_type} (id={action_id})',
                    extra={'msg_type': 'PENDING_ACTION_CLEARED'},
                )
            self._pending_action_info = None
        else:
            action_id = getattr(action, 'id', 'unknown')
            action_type = type(action).__name__
            self.log(
                'debug',
                f'Set pending action: {action_type} (id={action_id})',
                extra={'msg_type': 'PENDING_ACTION_SET'},
            )
            self._pending_action_info = (action, time.time())

    def get_state(self) -> State:
        """Returns the current running state object.

        Returns:
            State: The current state object.
        """
        return self.state

    def set_initial_state(
        self,
        state: State | None,
        conversation_stats: ConversationStats,
        max_iterations: int,
        max_budget_per_task: float | None,
        confirmation_mode: bool = False,
    ):
        self.state_tracker.set_initial_state(
            self.id,
            state,
            conversation_stats,
            max_iterations,
            max_budget_per_task,
            confirmation_mode,
        )
        # Always load from the event stream to avoid losing history
        self.state_tracker._init_history(
            self.event_stream,
        )

    def get_trajectory(self, include_screenshots: bool = False) -> list[dict]:
        # state history could be partially hidden/truncated before controller is closed
        assert self._closed
        return self.state_tracker.get_trajectory(include_screenshots)

    def _is_stuck(self) -> bool:
        """Checks if the agent or its delegate is stuck in a loop.

        Returns:
            bool: True if the agent is stuck, False otherwise.
        """
        # check if delegate stuck
        if self.delegate and self.delegate._is_stuck():
            return True

        return self._stuck_detector.is_stuck(self.headless_mode)

    def attempt_loop_recovery(self) -> bool:
        """Attempts loop recovery when agent is stuck in a loop.
        Only supports CLI for now.

        Returns:
            bool: True if recovery was successful and agent should continue,
                  False if recovery failed or was not attempted.
        """
        # Check if we're in a loop
        if not self._stuck_detector.stuck_analysis:
            return False

        """Handle loop recovery in CLI mode by pausing the agent and presenting recovery options."""
        recovery_point = self._stuck_detector.stuck_analysis.loop_start_idx

        # Present loop detection message
        self.event_stream.add_event(
            LoopDetectionObservation(
                content=f"""⚠️  Agent detected in a loop!
Loop type: {self._stuck_detector.stuck_analysis.loop_type}
Loop detected at iteration {self.state.iteration_flag.current_value}
\nRecovery options:
/resume 1. Restart from before loop (preserves {recovery_point} events)
/resume 2. Restart with last user message (reuses your most recent instruction)
/exit. Quit directly
\nThe agent has been paused. Type '/resume 1', '/resume 2', or '/exit' to choose an option.
"""
            ),
            source=EventSource.ENVIRONMENT,
        )

        # Pause the agent using the same mechanism as Ctrl+P
        # This ensures consistent behavior and avoids event loop conflicts
        self.event_stream.add_event(
            ChangeAgentStateAction(AgentState.PAUSED),
            EventSource.ENVIRONMENT,  # Use ENVIRONMENT source to distinguish from user pause
        )
        return True

    def _prepare_metrics_for_frontend(self, action: Action) -> None:
        """Create a minimal metrics object for frontend display and log it.

        To avoid performance issues with long conversations, we only keep:
        - accumulated_cost: The current total cost
        - accumulated_token_usage: Accumulated token statistics across all API calls
        - max_budget_per_task: The maximum budget allowed for the task

        This includes metrics from both the agent's LLM and the condenser's LLM if it exists.

        Args:
            action: The action to attach metrics to
        """
        # Get metrics from agent LLM
        metrics = self.conversation_stats.get_combined_metrics()

        # Create a clean copy with only the fields we want to keep
        clean_metrics = Metrics()
        clean_metrics.accumulated_cost = metrics.accumulated_cost
        clean_metrics._accumulated_token_usage = copy.deepcopy(
            metrics.accumulated_token_usage
        )

        # Add max_budget_per_task to metrics
        if self.state.budget_flag:
            clean_metrics.max_budget_per_task = self.state.budget_flag.max_value

        action.llm_metrics = clean_metrics

        # Log the metrics information for debugging
        # Get the latest usage directly from the agent's metrics
        latest_usage = None
        if self.state.metrics.token_usages:
            latest_usage = self.state.metrics.token_usages[-1]

        accumulated_usage = self.state.metrics.accumulated_token_usage
        self.log(
            'debug',
            f'Action metrics - accumulated_cost: {metrics.accumulated_cost}, max_budget: {metrics.max_budget_per_task}, '
            f'latest tokens (prompt/completion/cache_read/cache_write): '
            f'{latest_usage.prompt_tokens if latest_usage else 0}/'
            f'{latest_usage.completion_tokens if latest_usage else 0}/'
            f'{latest_usage.cache_read_tokens if latest_usage else 0}/'
            f'{latest_usage.cache_write_tokens if latest_usage else 0}, '
            f'accumulated tokens (prompt/completion): '
            f'{accumulated_usage.prompt_tokens}/'
            f'{accumulated_usage.completion_tokens}',
            extra={'msg_type': 'METRICS'},
        )

    def __repr__(self) -> str:
        pending_action_info = '<none>'
        if (
            hasattr(self, '_pending_action_info')
            and self._pending_action_info is not None
        ):
            action, timestamp = self._pending_action_info
            action_id = getattr(action, 'id', 'unknown')
            action_type = type(action).__name__
            elapsed_time = time.time() - timestamp
            pending_action_info = (
                f'{action_type}(id={action_id}, elapsed={elapsed_time:.2f}s)'
            )

        return (
            f'AgentController(id={getattr(self, "id", "<uninitialized>")}, '
            f'agent={getattr(self, "agent", "<uninitialized>")!r}, '
            f'event_stream={getattr(self, "event_stream", "<uninitialized>")!r}, '
            f'state={getattr(self, "state", "<uninitialized>")!r}, '
            f'delegate={getattr(self, "delegate", "<uninitialized>")!r}, '
            f'_pending_action={pending_action_info})'
        )

    def _is_awaiting_observation(self) -> bool:
        events = self.event_stream.search_events(reverse=True)
        for event in events:
            if isinstance(event, AgentStateChangedObservation):
                result = event.agent_state == AgentState.RUNNING
                return result
        return False

    def _first_user_message(
        self, events: list[Event] | None = None
    ) -> MessageAction | None:
        """Get the first user message for this agent.

        For regular agents, this is the first user message from the beginning (start_id=0).
        For delegate agents, this is the first user message after the delegate's start_id.

        Args:
            events: Optional list of events to search through. If None, uses the event stream.

        Returns:
            MessageAction | None: The first user message, or None if no user message found
        """
        # If events list is provided, search through it
        if events is not None:
            return next(
                (
                    e
                    for e in events
                    if isinstance(e, MessageAction) and e.source == EventSource.USER
                ),
                None,
            )

        # Otherwise, use the original event stream logic with caching
        # Return cached message if any
        if self._cached_first_user_message is not None:
            return self._cached_first_user_message

        # Find the first user message
        self._cached_first_user_message = next(
            (
                e
                for e in self.event_stream.search_events(
                    start_id=self.state.start_id,
                )
                if isinstance(e, MessageAction) and e.source == EventSource.USER
            ),
            None,
        )
        return self._cached_first_user_message

    async def _perform_loop_recovery(
        self, stuck_analysis: StuckDetector.StuckAnalysis
    ) -> None:
        """Perform loop recovery by truncating memory and restarting from before the loop."""
        recovery_point = stuck_analysis.loop_start_idx

        # Truncate memory to the recovery point
        await self._truncate_memory_to_point(recovery_point)

        # Set agent state to AWAITING_USER_INPUT to allow user to provide new instructions
        await self.set_agent_state_to(AgentState.AWAITING_USER_INPUT)

        self.event_stream.add_event(
            LoopDetectionObservation(
                content="""✅ Loop recovery completed. Agent has been reset to before the loop.
You can now provide new instructions to continue.
"""
            ),
            source=EventSource.ENVIRONMENT,
        )

    async def _truncate_memory_to_point(self, recovery_point: int) -> None:
        """Truncate memory to the specified recovery point."""
        # Get all events from state history
        all_events = self.state.history

        if recovery_point >= len(all_events):
            return

        # Keep only events up to the recovery point
        events_to_keep = all_events[:recovery_point]

        # Update state history
        self.state.history = events_to_keep

        # Update end_id to reflect the truncation
        if events_to_keep:
            self.state.end_id = events_to_keep[-1].id
        else:
            self.state.end_id = -1

        # Clear any cached messages
        self._cached_first_user_message = None

    async def _restart_with_last_user_message(
        self, stuck_analysis: StuckDetector.StuckAnalysis
    ) -> None:
        """Restart the agent using the last user message as the new instruction."""

        # Find the last user message in the history
        last_user_message = None
        for event in reversed(self.state.history):
            if isinstance(event, MessageAction) and event.source == EventSource.USER:
                last_user_message = event
                break

        if last_user_message:
            # Truncate memory to just before the loop started
            recovery_point = stuck_analysis.loop_start_idx
            await self._truncate_memory_to_point(recovery_point)

            # Set agent state to RUNNING and re-use the last user message
            await self.set_agent_state_to(AgentState.RUNNING)

            # Re-use the last user message as the new instruction
            self.event_stream.add_event(
                LoopDetectionObservation(
                    content=f"""\n✅ Restarting with your last instruction: {last_user_message.content}
Agent is now continuing with the same task...
"""
                ),
                source=EventSource.ENVIRONMENT,
            )

            # Create a new action with the last user message
            new_action = MessageAction(
                content=last_user_message.content, wait_for_response=False
            )
            new_action._source = EventSource.USER  # type: ignore [attr-defined]

            # Process the action to restart the agent
            await self._handle_action(new_action)
        else:
            # If no user message found, fall back to regular recovery
            print('\n⚠️  No previous user message found. Using standard recovery.')
            await self._perform_loop_recovery(stuck_analysis)

    def save_state(self):
        self.state_tracker.save_state()

    def _emit_step_delta(self, start_snapshot: dict[str, Any], is_bounded: bool) -> None:
        """Emits a lifecycle step_delta heartbeat in bounded mode (Revised 7B)."""
        if not is_bounded or self.state.get_local_step() < 0:
            return

        current = {
            'step': self.state.get_local_step(),
            'validation_triggered': getattr(self, '_validation_triggered', False),
            'validation_completed': getattr(self, '_validation_completed', False),
            'stop_reason': self.state.stop_reason,
        }
        diff = {}
        for k, v in current.items():
            old = start_snapshot.get(k)
            if v != old:
                diff[k] = {'from': old, 'to': v}
        
        if diff:
            # Underwood Tracking (7C)
            self._heartbeat_presence['step_delta'] = True
            payload = json.dumps({
                'task_index': self._task_index,
                'delta': diff
            })
            self.event_stream.add_event(
                NullObservation(content=f'[LIFECYCLE:step_delta] {payload}'),
                EventSource.AGENT
            )

    def _build_bounded_audit_payload(self, projection: dict[str, Any] | None = None, graph_path: list[int] | None = None) -> dict[str, Any]:
        """Builds a minimal structured audit summary for bounded termination (Phase 9D)."""
        is_bounded = getattr(self.agent.config, 'bounded_mode', False)
        if not is_bounded:
            return {}

        sequence_length = len(self._task_sequence) if self._task_sequence else 1

        # Determine if no further task activations will occur in this sequence
        # Activation continues only if policy allows AND global budget remains
        is_continuing = self._should_activate_next_task() and not self._sequence_iterations_exceeded()
        sequence_terminal = not is_continuing

        # Sequence completed successfully only if the final task reaches validation_succeeded
        is_last_task = (self._task_index + 1 >= sequence_length)
        sequence_completed = (
            is_last_task and
            self.state.stop_reason == 'validation_succeeded'
        )

        return {
            'underwood_audit': {
                'stop_reason': self.state.stop_reason,
                'heartbeat_presence': self._heartbeat_presence.copy(),
                'final_step': self.state.get_local_step(),
                'is_bounded': True,
                'task_index': self._task_index,
                'sequence_length': sequence_length,
                'sequence_terminal': sequence_terminal,
                'path_terminal': sequence_terminal,
                'sequence_completed': sequence_completed,
                'sequence_snapshot': self._sequence_snapshot,
                'sequence_replay_boundaries': self._sequence_replay_boundaries.copy(),
                'executed_path': list(self._executed_path),
                'terminal_path': list(self._executed_path),
                'replay_verification': self._build_replay_verification(),
                'gate_evaluation': {
                    'gate_completed': self._pre_execution_gate_completed,
                    'gate_reason': self._pre_execution_gate_reason,
                    'gate_diagnostic': self._map_gate_reason_to_diagnostic(self._pre_execution_gate_reason)
                },
                'parameter_enforcement': {
                    'final_iteration_cap': self._enforced_max_iterations,
                    'final_bounded_mode': self._enforced_bounded_mode,
                    'enforcement_status': self._enforcement_status.copy()
                },
                'projection_diagnostic': self._build_projection_diagnostic(projection, graph_path),
                'path_divergence': self._monitor_path_divergence(graph_path),
                'simulation_audit': self._build_simulation_audit(projection, graph_path)
            }
        }

    def _get_current_task(self) -> str | None:
        """Returns the active task from the sequence or the baseline state instruction (Phase 8A)."""
        if self._task_sequence and 0 <= self._task_index < len(self._task_sequence):
            return self._task_sequence[self._task_index]
        return getattr(self.state, 'instruction', None)

    def _reset_task_boundary_state(self) -> None:
        """Clears task-local bounded execution residue between sequential or graph tasks (Phase 8B/14B).

        This helper handles 'transient' state only. It must NOT clear persistent sequence-level 
        or graph-level metadata such as '_task_graph' or '_sequence_replay_boundaries'.
        """
        self.state.stop_reason = None
        self._validation_triggered = False
        self._validation_completed = False
        self._pending_action = None

        # Reset task-local heartbeat tracking to its default bounded-safe state
        if getattr(self.agent.config, 'bounded_mode', False):
            self._heartbeat_presence = {
                'step_started': False,
                'step_completed': False,
                'termination_triggered': False,
                'step_delta': False
            }
        else:
            self._heartbeat_presence = {}

    def _sequence_should_terminate(self) -> bool:
        """Determines if the multi-task sequence should fail-fast (Phase 8D)."""
        failure_reasons = {
            'validation_failed',
            'max_turns_reached',
            'budget_exceeded',
            'runtime_error'
        }

        # Phase 20B: Defer fail-fast for validation_failed if a recovery edge exists (L3 Branching)
        if self.state.stop_reason == 'validation_failed':
            if self._find_next_graph_node(self._task_index, 'validation_failed') is not None:
                return False

        return self.state.stop_reason in failure_reasons

    def _should_activate_next_task(self) -> bool:
        """Determines if the controller should activate the next task in the sequence (Phase 9A)."""
        is_success = self.state.stop_reason == 'validation_succeeded'
        # Phase 20B: Additionally allow activation for validation_failed if a recovery edge exists
        has_recovery = (
            self.state.stop_reason == 'validation_failed' and
            self._find_next_graph_node(self._task_index, 'validation_failed') is not None
        )

        if not (is_success or has_recovery):
            return False

        if self._sequence_should_terminate():
            return False

        # Check if a successor exists (Graph or Linear)
        is_graph_active = bool(self._task_graph.get('nodes') or self._task_graph.get('edges'))
        if is_graph_active:
            return self._find_next_graph_node(self._task_index, self.state.stop_reason) is not None

        return self._task_index + 1 < len(self._task_sequence)

    async def _activate_next_task(self) -> None:
        """Performs the controller-owned transition to the next task (Phase 9A/14A)."""
        current_idx = self._task_index
        stop_reason = self.state.stop_reason

        # Determine if an explicit graph is active (Phase 13A)
        is_graph_active = bool(self._task_graph.get('nodes') or self._task_graph.get('edges'))

        if is_graph_active:
            # Deterministic Graph Traversal (Phase 14A)
            next_index = self._find_next_graph_node(current_idx, stop_reason)
            if next_index is None:
                # Fail-closed: terminate if graph traversal is undefined or ambiguous
                self.log('error', f'UNDERWOOD: graph traversal failed at Node {current_idx} with reason {stop_reason}; terminating sequence.')
                return
            self.log('info', f'UNDERWOOD: graph transition from Node {current_idx} to Node {next_index}')
        else:
            # Legacy Linear Sequence logic (Phase 9A compatibility)
            next_index = current_idx + 1
            self.log('info', f'UNDERWOOD: linear transition from Task {current_idx} to {next_index}')

        boundary_marker = {
            'prior_index': current_idx,
            'next_index': next_index,
            'stop_reason': stop_reason,
            'iteration': self.state.iteration_flag.current_value
        }
        self._sequence_replay_boundaries.append(boundary_marker)

        self._task_index = next_index
        self._executed_path.append(next_index)
        self._reset_task_boundary_state()
        await self.set_agent_state_to(AgentState.RUNNING)

    def _sequence_iterations_exceeded(self) -> bool:
        """Determines if the global sequence iteration ceiling has been reached (Phase 9C Revised)."""
        # Derive the sequence ceiling from the per-task bounded ceiling (10)
        # and the effective sequence length.
        seq_len = len(self._task_sequence) if self._task_sequence else 1
        global_ceiling = 10 * seq_len
        return self.state.iteration_flag.current_value >= global_ceiling

    def _capture_sequence_snapshot(self) -> None:
        """Captures a deterministic snapshot of the initial sequence state for replay (Phase 10A)."""
        if self._sequence_snapshot is not None:
            return

        is_bounded = getattr(self.agent.config, 'bounded_mode', False)
        is_graph_active = bool(self._task_graph.get('nodes') or self._task_graph.get('edges'))

        self._sequence_snapshot = {
            'task_sequence': list(self._task_sequence),
            'task_index': self._task_index,
            'bounded_mode': is_bounded,
            'instruction': getattr(self.state, 'instruction', None),
            # Phase 16D: Graph Snapshot
            'task_graph_active': is_graph_active,
            'task_graph': {
                'nodes': list(self._task_graph.get('nodes', [])),
                'edges': [dict(e) for e in self._task_graph.get('edges', [])]
            } if is_graph_active else None,
            # Phase 17C: Parameter Snapshot
            'requested_execution_params': {
                'max_iterations': getattr(self.agent.config, 'max_iterations', None),
                'bounded_mode': getattr(self.agent.config, 'bounded_mode', None)
            },
            'enforced_execution_params': {
                'max_iterations': self._enforced_max_iterations,
                'bounded_mode': self._enforced_bounded_mode
            }
        }

    def _build_replay_verification(self) -> dict[str, Any]:
        """Provides minimal verification signals for sequence replay certification (Phase 10D/16E)."""
        is_bounded = getattr(self.agent.config, 'bounded_mode', False)
        is_graph_active = bool(self._task_graph.get('nodes') or self._task_graph.get('edges'))
        snapshot = self._sequence_snapshot

        # Phase 16E: Structural Consistency Verification
        graph_structure_consistent = False
        if snapshot is not None:
            snap_graph_active = snapshot.get('task_graph_active', False)
            if not snap_graph_active and not is_graph_active:
                # Both indicate baseline linear mode
                graph_structure_consistent = True
            elif snap_graph_active == is_graph_active:
                # Compare structural contents of controller-owned graph state
                snap_graph = snapshot.get('task_graph', {})
                graph_structure_consistent = (
                    snap_graph.get('nodes') == self._task_graph.get('nodes') and
                    snap_graph.get('edges') == self._task_graph.get('edges')
                )

        return {
            'snapshot_present': snapshot is not None,
            'boundary_count': len(self._sequence_replay_boundaries),
            'bounded_mode_consistent': snapshot.get('bounded_mode') == is_bounded if snapshot else False,
            'task_index_consistent': (snapshot.get('task_index', 0) <= self._task_index) if snapshot else False,
            # Phase 16D parity
            'graph_presence_consistent': (snapshot.get('task_graph_active') == is_graph_active) if snapshot else False,
            # Phase 17C entries
            'parameters_consistent': (
                snapshot.get('enforced_execution_params', {}).get('max_iterations') == self._enforced_max_iterations and
                snapshot.get('enforced_execution_params', {}).get('bounded_mode') == self._enforced_bounded_mode
            ) if snapshot else False,
            # Phase 16E entries
            'graph_structure_consistent': graph_structure_consistent
        }

    def _build_simulation_state(self) -> dict[str, Any]:
        """Constructs an isolated, shadow simulation state from the sequence snapshot (Phase 11A)."""
        if self._sequence_snapshot is None:
            return {}

        snapshot = self._sequence_snapshot

        # Ensure deep copy of boundaries to prevent cross-contamination
        boundaries = [dict(b) for b in self._sequence_replay_boundaries]

        return {
            'task_sequence': list(snapshot.get('task_sequence', [])),
            'task_graph': {
                'nodes': list(self._task_graph.get('nodes', [])),
                'edges': [dict(e) for e in self._task_graph.get('edges', [])]
            },
            'initial_task_index': snapshot.get('task_index'),
            'bounded_mode': snapshot.get('bounded_mode'),
            'instruction': snapshot.get('instruction'),
            'replay_boundaries': boundaries,
            'max_steps_per_task': 10,
            'sequence_length': len(snapshot.get('task_sequence', []))
        }

    def _simulate_sequence_boundaries(self) -> list[dict[str, Any]]:
        """Produces a deterministic simulated boundary progression for the sequence (Phase 11B)."""
        sim_state = self._build_simulation_state()
        if not sim_state:
            return []

        replay_boundaries = sim_state.get('replay_boundaries', [])
        simulated_progression = []

        for boundary in replay_boundaries:
            # Construct a detached simulated entry for each boundary marker
            sim_entry = {
                'prior_index': boundary.get('prior_index'),
                'next_index': boundary.get('next_index'),
                'stop_reason': boundary.get('stop_reason'),
                'iteration': boundary.get('iteration'),
                'simulated_reset_applied': True
            }
            simulated_progression.append(sim_entry)

        return simulated_progression

    def _project_sequence_budget(self, graph_path: list[int] | None = None) -> dict[str, Any]:
        """Projects sequence-level bounded budget usage from simulation state (Phase 11C/16C)."""
        sim_state = self._build_simulation_state()
        if not sim_state:
            return {}

        # Underwood Graph-Aware Projection (16C)
        is_graph_active = bool(self._task_graph.get('nodes') or self._task_graph.get('edges'))
        if is_graph_active:
             # Use precomputed path if available, otherwise simulate
             path = graph_path if graph_path is not None else self._simulate_graph_path()
             seq_len = len(path)
        else:
             seq_len = sim_state.get('sequence_length', 1)

        max_per_task = sim_state.get('max_steps_per_task', 10)
        boundaries = sim_state.get('replay_boundaries', [])

        return {
            'sequence_length': seq_len,
            'max_steps_per_task': max_per_task,
            'projected_max_total_steps': seq_len * max_per_task,
            'recorded_boundary_count': len(boundaries),
            # Guard semantics (Phase 9C/16C): ceiling = 10 * seq_len
            'projected_iteration_ceiling': 10 * seq_len
        }

    def _build_simulation_audit(self, projection: dict[str, Any] | None = None, graph_path: list[int] | None = None) -> dict[str, Any]:
        """Provides a structured summary of the pre-execution simulation state (Phase 11D/15B)."""
        sim_state = self._build_simulation_state()
        if not sim_state:
            return {}

        return {
            'underwood_simulation': {
                'simulation_available': True,
                'simulation_state': sim_state,
                'simulated_boundaries': self._simulate_sequence_boundaries(),
                'budget_projection': projection or self._project_sequence_budget(),
                'projection_summary': self._build_projection_diagnostic(projection, graph_path)
            }
        }

    def _evaluate_sequence_gates(self) -> tuple[bool, str | None, dict[str, Any] | None, list[int] | None]:
        """Evaluates deterministic gating policies against sequence simulation projections (Phase 12A/16C)."""
        # Determine graph path first to optimize and satisfy Phase 16C unified projection requirement
        is_graph_active = bool(self._task_graph.get('nodes') or self._task_graph.get('edges'))
        graph_path = self._simulate_graph_path() if is_graph_active else None
        
        # Pass derived path into budget projection to avoid recomputation
        projection = self._project_sequence_budget(graph_path=graph_path)
        if not projection:
            return False, 'simulation_unavailable', None, None

        # Policy Gate: Basic sequence structure consistency (Phase 12A)
        if projection.get('sequence_length', 0) > 100:
            return False, 'excessive_sequence_length', projection, graph_path

        # Policy Gate: Projection must not exceed absolute controller iteration budget (Phase 12A/17C)
        max_total_steps = projection.get('projected_max_total_steps', 0)
        ambient_limit = self._enforced_max_iterations
        if max_total_steps > ambient_limit:
            return False, f'projected_steps_exceed_budget:{max_total_steps}>{ambient_limit}', projection, graph_path

        # Policy Gate: Projected iteration ceiling must be within allowed bounds (Phase 9C/12A/17C)
        projected_ceiling = projection.get('projected_iteration_ceiling', 0)
        if projected_ceiling > ambient_limit:
            return False, f'projected_ceiling_exceed_budget:{projected_ceiling}>{ambient_limit}', projection, graph_path

        # Policy Gate: Deterministic Graph Admissibility (Phase 13D/16B Revision)
        if is_graph_active:
            if not graph_path:
                return False, 'graph_structure_non_traversable', projection, None

            # Re-verify path against absolute budget using graph-aware path metrics
            graph_len = len(graph_path)
            projected_graph_ceiling = 10 * graph_len
            if projected_graph_ceiling > ambient_limit:
                return False, f'graph_path_ceiling_exceed_budget:{projected_graph_ceiling}>{ambient_limit}', projection, graph_path

        return True, None, projection, graph_path

    async def _run_pre_execution_gate(self) -> None:
        """Executes the one-time blocking decision gate before live sequence activation (Phase 12B/17B)."""
        if self._pre_execution_gate_completed:
            return

        # Phase 17B/C: Execution Parameter Enforcement
        if not self._enforce_execution_parameters():
            self._pre_execution_gate_reason = 'invalid_execution_parameters'
            self.state.stop_reason = 'gate_refusal'
            # Terminate with refusal metadata and terminal diagnostics
            audit_payload = self._build_bounded_audit_payload()
            self._emit_terminal_audit_analytics(audit_payload)
            self.state.outputs = {
                'error': 'Sequence execution gated',
                'gate_reason': self._pre_execution_gate_reason,
                'gate_diagnostic': self._map_gate_reason_to_diagnostic(self._pre_execution_gate_reason),
                'bounded_audit': audit_payload
            }
            await self.set_agent_state_to(AgentState.FINISHED)
            self._pre_execution_gate_completed = True
            return

        # Underwood Graph Admission (16B)
        external_graph = getattr(self.agent.config, 'task_graph', None)
        if external_graph is not None:
            if not self._admit_task_graph(external_graph):
                # Specific gate reason is now set authoritatively inside _admit_task_graph
                self.state.stop_reason = 'gate_refusal'
                # Terminate with refusal metadata and terminal diagnostics
                audit_payload = self._build_bounded_audit_payload()
                self._emit_terminal_audit_analytics(audit_payload)
                self.state.outputs = {
                    'error': 'Sequence execution gated',
                    'gate_reason': self._pre_execution_gate_reason,
                    'gate_diagnostic': self._map_gate_reason_to_diagnostic(self._pre_execution_gate_reason),
                    'bounded_audit': audit_payload
                }
                await self.set_agent_state_to(AgentState.FINISHED)
                self._pre_execution_gate_completed = True
                return

        passed, reason, proj, path = self._evaluate_sequence_gates()
        self._pre_execution_gate_completed = True

        if not passed:
            self._pre_execution_gate_reason = reason
            diagnostic = self._map_gate_reason_to_diagnostic(reason)
            self.log('error', f'UNDERWOOD: sequence execution blocked by pre-execution gate: {diagnostic}')
            self.state.stop_reason = 'gate_refusal'
            # Terminate immediately with refusal metadata
            audit_payload = self._build_bounded_audit_payload(proj, path)
            self._emit_terminal_audit_analytics(audit_payload)
            self.state.outputs = {
                'error': 'Sequence execution gated',
                'gate_reason': reason,
                'gate_diagnostic': diagnostic,
                'bounded_audit': audit_payload
            }
            await self.set_agent_state_to(AgentState.FINISHED)
            return

        self.log('info', 'UNDERWOOD: sequence cleared pre-execution gates; ready for activation')

        proj_diag = self._build_projection_diagnostic(proj, path)
        path_desc = f"Path: {proj_diag.get('projected_path_length')} steps"
        if proj_diag.get('is_graph_path'):
            path_desc += " (Graph Traversal)"
        else:
            path_desc += " (Linear Sequence)"
        
        self.log('info', f'UNDERWOOD: projection summary: {path_desc}; projected total steps: ~{proj_diag.get("projected_steps")}')

    def _build_projection_diagnostic(self, projection: dict[str, Any] | None = None, graph_path: list[int] | None = None) -> dict[str, Any]:
        """Derives a concise operator-facing projection summary (Phase 15B/16C)."""
        is_graph = bool(self._task_graph.get('nodes') or self._task_graph.get('edges'))
        
        # Ensure authoritative path derivation if not provided (Phase 16C)
        path = graph_path if graph_path is not None else (self._simulate_graph_path() if is_graph else [])
        
        # Sync projection to the graph-aware path if needed
        proj = projection or self._project_sequence_budget(graph_path=path if is_graph else None)
        
        return {
            'projected_steps': proj.get('projected_max_total_steps', 0),
            'projected_iteration_ceiling': proj.get('projected_iteration_ceiling', 0),
            'projected_path_length': len(path) if is_graph else len(self._task_sequence),
            'is_graph_path': is_graph,
            'terminal_expectation': True if (path or self._task_sequence) else False
        }


    def _monitor_path_divergence(self, graph_path: list[int] | None = None) -> dict[str, Any]:
        """Provides a passive diagnostic comparison between projected and actual execution paths (Phase 15C Revised)."""
        is_graph = bool(self._task_graph.get('nodes') or self._task_graph.get('edges'))

        # Use provided projection if available to avoid recomputation
        if is_graph:
            expected = graph_path if graph_path is not None else self._simulate_graph_path()
        else:
            # For linear sequences, the expected path is a simple increment from the start point
            start_idx = self._sequence_snapshot.get('task_index', 0) if self._sequence_snapshot else 0
            seq_len = len(self._task_sequence)
            expected = list(range(start_idx, seq_len))

        actual = self._executed_path
        diverged = False
        div_idx = -1
        expected_node = None
        actual_node = None

        # 1. Check for mismatch or actual-longer-than-expected
        for i, val in enumerate(actual):
            if i >= len(expected):
                # Runtime went beyond simulated projection
                diverged = True
                div_idx = i
                actual_node = val
                break
            if val != expected[i]:
                # Branching mismatch
                diverged = True
                div_idx = i
                expected_node = expected[i]
                actual_node = val
                break

        # 2. Check for actual-shorter-than-expected (if terminal)
        # If the run has stopped but hasn't reached the projected terminal node
        # Derive terminal condition from existing iteration/activation logic (Phase 14D alignment)
        is_continuing = self._should_activate_next_task() and not self._sequence_iterations_exceeded()
        sequence_terminal = not is_continuing

        if not diverged and sequence_terminal and len(actual) < len(expected):
            diverged = True
            div_idx = len(actual)
            expected_node = expected[len(actual)]
            # actual_node remains None to indicate early termination

        return {
            'diverged': diverged,
            'divergence_index': div_idx if diverged else None,
            'expected_node': expected_node,
            'actual_node': actual_node
        }

    def _admit_task_graph(self, graph: dict | None) -> bool:
        """Validates and admits an external task graph into the controller (Phase 16B/18B)."""
        if not graph:
            return True

        nodes = graph.get('nodes', [])
        edges = graph.get('edges', [])

        # 1. Node validation: non-empty, bounded, string instructions (16B)
        if not isinstance(nodes, list) or not (1 <= len(nodes) <= 100):
            self.log('error', f'UNDERWOOD: graph admission failed: invalid node count ({len(nodes) if isinstance(nodes, list) else "not a list"})')
            self._pre_execution_gate_reason = 'graph_admission_failed'
            return False
        
        if not all(isinstance(n, str) for n in nodes):
            self.log('error', 'UNDERWOOD: graph admission failed: nodes must be task instruction strings')
            self._pre_execution_gate_reason = 'graph_admission_failed'
            return False

        # 2. Boundary Hardening: Payload Size (Phase 18B)
        total_payload = sum(len(n) for n in nodes)
        if total_payload > 64000:
            self.log('error', f'UNDERWOOD: graph admission failed: payload size {total_payload} exceeds 64KB limit')
            self._pre_execution_gate_reason = 'graph_payload_exceeded'
            return False

        # 3. Edge validation: list of dicts (16B)
        if not isinstance(edges, list):
            self.log('error', 'UNDERWOOD: graph admission failed: edges must be a list')
            self._pre_execution_gate_reason = 'graph_admission_failed'
            return False

        # 4. Boundary Hardening: Edge Density (Phase 18B)
        if len(edges) > 2 * len(nodes):
            self.log('error', f'UNDERWOOD: graph admission failed: edge density {len(edges)} exceeds limit for {len(nodes)} nodes')
            self._pre_execution_gate_reason = 'graph_density_exceeded'
            return False

        valid_conditions = {None, 'on_success', 'on_failure'}
        seen_transitions = set()

        for idx, edge in enumerate(edges):
            if not isinstance(edge, dict):
                self.log('error', f'UNDERWOOD: graph admission failed: edge {idx} is not a dictionary')
                return False
            
            f = edge.get('from')
            t = edge.get('to')
            c = edge.get('condition')

            # Index integrity: from/to must be valid node indices
            if not isinstance(f, int) or not (0 <= f < len(nodes)):
                self.log('error', f'UNDERWOOD: graph admission failed: edge {idx} "from" index {f} out of bounds')
                return False
            if not isinstance(t, int) or not (0 <= t < len(nodes)):
                self.log('error', f'UNDERWOOD: graph admission failed: edge {idx} "to" index {t} out of bounds')
                return False
            
            # Condition typing
            if c not in valid_conditions:
                self.log('error', f'UNDERWOOD: graph admission failed: edge {idx} "condition" {c} is invalid')
                return False

            # Determinism: At most one outbound edge per (node, condition)
            transition = (f, c)
            if transition in seen_transitions:
                self.log('error', f'UNDERWOOD: graph admission failed: non-deterministic transition at Node {f} for condition {c}')
                return False
            seen_transitions.add(transition)

        # 5. Boundary Hardening: Cycle Detection (Phase 18B)
        if self._has_graph_cycles(nodes, edges):
            self.log('error', 'UNDERWOOD: graph admission failed: cyclic structure detected')
            self._pre_execution_gate_reason = 'graph_cycle_detected'
            return False

        # 6. Admission: Normalize to controller state and synchronize compatibility mirrors (16B)
        self._task_graph = {
            'nodes': list(nodes),
            'edges': [dict(e) for e in edges]
        }
        self._task_sequence = list(nodes)
        
        # Reset graph starting state for the new admission
        self._task_index = 0
        self._executed_path = [0]
        
        self.log('info', f'UNDERWOOD: graph admitted successfully ({len(nodes)} nodes, {len(edges)} edges)')
        return True

    def _enforce_execution_parameters(self) -> bool:
        """Deterministically validates and clamps external execution parameters (Phase 17B/C)."""
        requested_iterations = getattr(self.agent.config, 'max_iterations', 200)
        requested_bounded = getattr(self.agent.config, 'bounded_mode', False)
        
        # Internal Authority Hard Caps
        HARD_CAP_ITERATIONS = 200
        POLICY_REQUIRED_BOUNDED = True # In Tradjinn/Underwood, bounded mode is the required state
        
        # 1. max_iterations enforcement
        if requested_iterations <= 0:
            self._enforcement_status['max_iterations'] = 'rejected'
            return False
        
        if requested_iterations > HARD_CAP_ITERATIONS:
            self._enforced_max_iterations = HARD_CAP_ITERATIONS
            self._enforcement_status['max_iterations'] = 'clamped'
        else:
            self._enforced_max_iterations = requested_iterations
            self._enforcement_status['max_iterations'] = 'validated'
            
        # 2. bounded_mode enforcement (authoritative ignore policy)
        if not requested_bounded and POLICY_REQUIRED_BOUNDED:
            self._enforced_bounded_mode = True
            self._enforcement_status['bounded_mode'] = 'ignored'
        else:
            self._enforced_bounded_mode = requested_bounded
            self._enforcement_status['bounded_mode'] = 'validated'
            
        return True

    def _has_graph_cycles(self, nodes: list[str], edges: list[dict[str, Any]]) -> bool:
        """Deterministically detects cycles in the task graph using a recursion stack (Phase 18B)."""
        adj = {i: [] for i in range(len(nodes))}
        for edge in edges:
            adj[edge['from']].append(edge['to'])
        
        visited = set()
        rec_stack = set()
        
        def visit(n):
            if n in rec_stack:
                return True
            if n in visited:
                return False
            
            visited.add(n)
            rec_stack.add(n)
            for neighbor in adj[n]:
                if visit(neighbor):
                    return True
            rec_stack.remove(n)
            return False
        
        for i in range(len(nodes)):
            if visit(i):
                return True
        return False

    def _emit_terminal_audit_analytics(self, payload: dict[str, Any]) -> None:
        """Emits concise operator-facing terminal diagnostics derived from the audit payload (Phase 15D)."""
        audit = payload.get('underwood_audit', {})
        if not audit:
            return

        reason = audit.get('stop_reason', 'unknown')
        status = "TERMINAL" if audit.get('path_terminal') else "INTERMEDIATE"
        gate = audit.get('gate_evaluation', {})
        divergence = audit.get('path_divergence', {})

        summary = f"UNDERWOOD AUDIT [{status}]: reason={reason}"
        if gate.get('gate_completed') and gate.get('gate_reason'):
            summary += f"; gate_refusal={gate.get('gate_reason')}"

        if divergence.get('diverged'):
            summary += f"; PATH_DIVERGENCE at index {divergence.get('divergence_index')}"

        self.log('info', summary)

    def _map_gate_reason_to_diagnostic(self, reason: str | None) -> str:
        """Translates machine-readable gate reasons into operator-facing diagnostic summaries (Phase 15A)."""
        if not reason:
            return "Admission gate cleared: task sequence adheres to bounded policies."

        mapping = {
            'simulation_unavailable': "Sequence simulation failed or unavailable; check controller context.",
            'excessive_sequence_length': "Sequence length exceeds policy limits (>100 tasks).",
            'graph_structure_non_traversable': "Execution graph is structurally empty or non-traversable.",
            'graph_admission_failed': "Dynamic graph injection failed validation; graph structure is malformed or violates determinism contract.",
            'invalid_execution_parameters': "Supplied execution parameters are malformed or violate controller-owned safety policies.",
            'graph_density_exceeded': "Graph edge density exceeds the authoritative safety threshold (2x nodes).",
            'graph_payload_exceeded': "Total instruction payload size exceeds the 64KB safety limit.",
            'graph_cycle_detected': "Cyclic graph structure detected; all submitted graphs must be strictly non-cyclic.",
        }

        # Handle parameterized reasons
        if reason.startswith('projected_steps_exceed_budget:'):
            val = reason.split(':')[-1]
            return f"Projected iteration budget exceeded (Actual: {val})."
        if reason.startswith('projected_ceiling_exceed_budget:'):
            val = reason.split(':')[-1]
            return f"Projected iteration ceiling exceeded (Actual: {val})."
        if reason.startswith('graph_path_ceiling_exceed_budget:'):
            val = reason.split(':')[-1]
            return f"Projected graph path ceiling exceeded (Actual: {val})."

        return mapping.get(reason, f"Access denied by pre-execution gate (Reason: {reason}).")

    def _find_next_graph_node(self, from_idx: int, stop_reason: str | None) -> int | None:
        """Internal helper to determine the next task node based on explicit edges and outcomes (Phase 13 Revision)."""
        edges = self._task_graph.get('edges', [])
        matching_tos = []
        for edge in edges:
            if edge.get('from') != from_idx:
                continue

            to_node = edge.get('to')
            condition = edge.get('condition')

            if not condition:
                matching_tos.append(to_node)
            elif condition == 'on_success' and stop_reason == 'validation_succeeded':
                matching_tos.append(to_node)
            elif condition == 'on_failure' and stop_reason and stop_reason != 'validation_succeeded':
                matching_tos.append(to_node)

        return matching_tos[0] if len(matching_tos) == 1 else None

    def _get_next_graph_node(self) -> int | None:
        """Determines the next task node from explicit graph edges (Phase 13B)."""
        if not self._task_graph.get('nodes') or not self._task_graph.get('edges'):
            return None
        return self._find_next_graph_node(self._task_index, self.state.stop_reason)

    def _simulate_graph_path(self) -> list[int]:
        """Projects the deterministic graph path from the current index (Phase 13C/19B)."""
        if not self._task_graph.get('nodes'):
            return []

        path = [self._task_index]
        visited = {self._task_index}
        current_node = self._task_index
        is_first_step = True

        while True:
            # For simulation, assume success unless we have an active stop_reason at the current step (Phase 19B)
            sr = (self.state.stop_reason if is_first_step and self.state.stop_reason is not None 
                  else 'validation_succeeded')
            next_node = self._find_next_graph_node(current_node, sr)

            if next_node is None or next_node in visited:
                break

            path.append(next_node)
            visited.add(next_node)
            current_node = next_node
            is_first_step = False

        return path
