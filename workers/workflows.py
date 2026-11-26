from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class AgentWorkflow:
    def __init__(self) -> None:
        self.cancel_requested = False
        self.wake = False

    @workflow.signal
    async def cancel(self) -> None:
        self.cancel_requested = True
        self.wake = True

    @workflow.signal
    async def resume(self) -> None:
        self.wake = True

    @workflow.run
    async def run(self, run_id: str, tenant_id: str) -> str:
        while True:
            if self.cancel_requested:
                cancelled_state: str = await workflow.execute_activity(
                    "cancel_run",
                    result_type=str,
                    args=[run_id, tenant_id],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                return cancelled_state
            self.wake = False
            state: str = await workflow.execute_activity(
                "advance_run",
                result_type=str,
                args=[run_id, tenant_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
            if state in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "BUDGET_EXHAUSTED"}:
                return state
            if state == "WAITING_APPROVAL":
                # Poll persisted approvals as well as signals; a lost signal cannot strand a run.
                try:
                    await workflow.wait_condition(lambda: self.wake, timeout=timedelta(seconds=10))
                except TimeoutError:
                    pass
