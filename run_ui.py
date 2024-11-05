import json
from functools import wraps
import os
from pathlib import Path
import threading
from quart import Quart, request, jsonify, Response
from agent import AgentContext
from initialize import initialize
from python.helpers import files
from python.helpers.files import get_abs_path
from python.helpers.print_style import PrintStyle
from python.helpers.dotenv import load_dotenv
from python.helpers import persist_chat

# initialize the internal Quart server
app = Quart("app", static_folder=get_abs_path("./webui"), static_url_path="/")
app.config["JSON_SORT_KEYS"] = False  # Disable key sorting in jsonify

lock = threading.Lock()


# Basic Authentication setup
def check_auth(username, password):
    return username == os.environ.get(
        "BASIC_AUTH_USERNAME", "admin"
    ) and password == os.environ.get("BASIC_AUTH_PASSWORD", "admin")


def authenticate():
    return Response(
        "Could not verify your access level for that URL.\n"
        "You have to login with proper credentials.",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'},
    )


def requires_auth(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return await f(*args, **kwargs)

    return decorated


# Use absolute path for CONFIG_FILE
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_selected_models():
    if not os.path.exists(CONFIG_FILE):
        return {
            "chat_model": "gpt-4o-mini",
            "utility_model": "gpt-4o-mini",
            "embedding_model": "text-embedding-3-small",
        }
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def save_selected_models(models):
    with open(CONFIG_FILE, "w") as f:
        json.dump(models, f, indent=4)


@app.route("/api/models", methods=["GET"])
async def get_models():
    selected_models = load_selected_models()
    print(f"Loaded models: {selected_models}")  # Debugging Statement
    return jsonify(selected_models), 200


@app.route("/api/models", methods=["POST"])
async def update_models():
    data = await request.get_json()
    required_keys = {"chat_model", "utility_model", "embedding_model"}
    if not required_keys.issubset(data.keys()):
        return jsonify({"error": "Missing model parameters"}), 400
    save_selected_models(data)
    # Reinitialize AgentConfig if necessary
    try:
        config = initialize(
            chat_model=data["chat_model"],
            utility_model=data["utility_model"],
            embedding_model=data["embedding_model"],
        )
        print(f"Updated models: {data}")  # Debugging Statement
        return jsonify({"message": "Models updated successfully"}), 200
    except Exception as e:
        print(f"Error initializing models: {e}")  # Debugging Statement
        return jsonify({"error": str(e)}), 500


# get context to run agent zero in
def get_context(ctxid: str):
    with lock:
        if not ctxid:
            first = AgentContext.first()
            if first:
                return first
            return AgentContext(config=initialize())
        got = AgentContext.get(ctxid)
        if got:
            return got
        return AgentContext(config=initialize(), id=ctxid)


# handle default address, show demo html page from ./test_form.html
@app.route("/", methods=["GET"])
@requires_auth
async def test_form():
    return Path(get_abs_path("./webui/index.html")).read_text()


# simple health check, just return OK to see the server is running
@app.route("/ok", methods=["GET", "POST"])
async def health_check():
    return "OK"


# # secret page, requires authentication
# @app.route('/secret', methods=['GET'])
# @requires_auth
# async def secret_page():
#     return Path("./secret_page.html").read_text()


# send message to agent (async UI)
@app.route("/msg", methods=["POST"])
async def handle_message_async():
    result = await handle_message(False)
    return result


# send message to agent (synchronous API)
@app.route("/msg_sync", methods=["POST"])
async def handle_msg_sync():
    result = await handle_message(True)
    return result


async def handle_message(sync: bool):
    try:

        # data sent to the server
        input = await request.get_json()
        text = input.get("text", "")
        ctxid = input.get("context", "")
        blev = input.get("broadcast", 1)

        # context instance - get or create
        context = get_context(ctxid)

        # print to console and log
        PrintStyle(
            background_color="#6C3483", font_color="white", bold=True, padding=True
        ).print(f"User message:")
        PrintStyle(font_color="white", padding=False).print(f"> {text}")
        context.log.log(type="user", heading="User message", content=text)

        if sync:
            context.communicate(text)
            result = await context.process.result()  # type: ignore
            response = {
                "ok": True,
                "message": result,
                "context": context.id,
            }
        else:

            context.communicate(text)
            response = {
                "ok": True,
                "message": "Message received.",
                "context": context.id,
            }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }
        PrintStyle.error(str(e))

    # respond with json
    return jsonify(response)


# pausing/unpausing the agent
@app.route("/pause", methods=["POST"])
async def pause():
    result = await pause_async()
    return result


async def pause_async():
    try:

        # data sent to the server
        input = await request.get_json()
        paused = input.get("paused", False)
        ctxid = input.get("context", "")

        # context instance - get or create
        context = get_context(ctxid)

        context.paused = paused

        response = {
            "ok": True,
            "message": "Agent paused." if paused else "Agent unpaused.",
            "pause": paused,
        }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }
        PrintStyle.error(str(e))

    # respond with json
    return jsonify(response)


# load chats from json
@app.route("/loadChats", methods=["POST"])
async def load_chats():
    result = await load_chats_async()
    return result


async def load_chats_async():
    try:
        # data sent to the server
        input = await request.get_json()
        chats = input.get("chats", [])
        if not chats:
            raise Exception("No chats provided")

        ctxids = persist_chat.load_json_chats(chats)

        response = {
            "ok": True,
            "message": "Chats loaded.",
            "ctxids": ctxids,
        }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }
        PrintStyle.error(str(e))

    # respond with json
    return jsonify(response)


# load chats from json
@app.route("/exportChat", methods=["POST"])
async def export_chat():
    result = await export_chat_async()
    return result


async def export_chat_async():
    try:
        # data sent to the server
        input = await request.get_json()
        ctxid = input.get("ctxid", "")
        if not ctxid:
            raise Exception("No context id provided")

        context = get_context(ctxid)
        content = persist_chat.export_json_chat(context)

        response = {
            "ok": True,
            "message": "Chats loaded.",
            "ctxid": context.id,
            "content": content,
        }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }
        PrintStyle.error(str(e))

    # respond with json
    return jsonify(response)


# restarting with new agent0
@app.route("/reset", methods=["POST"])
async def reset():
    result = await reset_async()
    return result


async def reset_async():
    try:

        # data sent to the server
        input = await request.get_json()
        ctxid = input.get("context", "")

        # context instance - get or create
        context = get_context(ctxid)
        context.reset()
        persist_chat.save_tmp_chat(context)

        response = {
            "ok": True,
            "message": "Agent restarted.",
        }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }
        PrintStyle.error(str(e))

    # respond with json
    return jsonify(response)


# killing context
@app.route("/remove", methods=["POST"])
async def remove():
    result = await remove_async()
    return result


async def remove_async():
    try:

        # data sent to the server
        input = await request.get_json()
        ctxid = input.get("context", "")

        # context instance - get or create
        AgentContext.remove(ctxid)
        persist_chat.remove_chat(ctxid)

        response = {
            "ok": True,
            "message": "Context removed.",
        }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }
        PrintStyle.error(str(e))

    # respond with json
    return jsonify(response)


# Web UI polling
@app.route("/poll", methods=["POST"])
async def poll():
    result = await poll_async()
    return result


async def poll_async():
    try:

        # data sent to the server
        input = await request.get_json()
        ctxid = input.get("context", None)
        from_no = input.get("log_from", 0)

        # context instance - get or create
        context = get_context(ctxid)

        logs = context.log.output(start=from_no)

        # loop AgentContext._contexts
        ctxs = []
        for ctx in AgentContext._contexts.values():
            ctxs.append(
                {
                    "id": ctx.id,
                    "no": ctx.no,
                    "log_guid": ctx.log.guid,
                    "log_version": len(ctx.log.updates),
                    "log_length": len(ctx.log.logs),
                    "paused": ctx.paused,
                }
            )

        # data from this server
        response = {
            "ok": True,
            "context": context.id,
            "contexts": ctxs,
            "logs": logs,
            "log_guid": context.log.guid,
            "log_version": len(context.log.updates),
            "log_progress": context.log.progress,
            "paused": context.paused,
        }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }
        PrintStyle.error(str(e))

    # serialize json with json.dumps to preserve OrderedDict order
    response_json = json.dumps(response)
    return Response(response=response_json, status=200, mimetype="application/json")
    # return jsonify(response)


@app.route("/protected")
@requires_auth
async def protected():
    return jsonify({"message": "This is protected content!"})


def run():
    print("Initializing framework...")

    # load env vars
    load_dotenv()

    # initialize contexts from persisted chats
    persist_chat.load_tmp_chats()

    # Suppress only request logs but keep the startup messages
    from werkzeug.serving import WSGIRequestHandler

    class NoRequestLoggingWSGIRequestHandler(WSGIRequestHandler):
        def log_request(self, code="-", size="-"):
            pass  # Override to suppress request logging

    # run the server on port from .env
    port = int(os.environ.get("WEB_UI_PORT", 0)) or None
    app.run(request_handler=NoRequestLoggingWSGIRequestHandler, port=port)


# run the internal server
if __name__ == "__main__":
    run()
