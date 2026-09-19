from concurrent.futures import ThreadPoolExecutor
import traceback

from src.database import update_job


# The ML pipeline is resource intensive and currently uses local model instances.
# A single worker prevents concurrent jobs from overwriting resources or exhausting RAM.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meeting-ai-job")


def submit_job(job_id: str, task, cleanup=None):
    def run():
        update_job(job_id, status="running")
        try:
            task()
        except Exception as exc:
            update_job(
                job_id,
                status="error",
                message=str(exc),
                error_detail=traceback.format_exc(),
            )
        finally:
            if cleanup:
                cleanup()

    return _executor.submit(run)
