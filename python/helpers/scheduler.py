from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import time
from python.api.message_async import MessageAsync, Message
from flask import Request
from run_ui import app, lock

# Create a single instance of BackgroundScheduler
scheduler = AsyncIOScheduler()
# TODO: configure scheduler for persistence and other settings
scheduler.start()  # Start the scheduler immediately


class SchedulingRequest(Request):

    @property
    def is_json(self):
        return self._is_json

    def get_json(self, /, force=False, silent=False, cache=None) -> dict:
        return self._json

    @property
    def content_type(self) -> str:
        return self._content_type

    def __init__(self, json: dict, **kwargs):
        self._is_json = True
        self._json = json
        self._content_type = "application/json"


async def scheduled_task(request: SchedulingRequest):
    print("Executing scheduled task")
    async_message = Message(app, lock)
    print("Scheduled task executed")
    result = await async_message.handle_request(request)
    print("result: ", result)
