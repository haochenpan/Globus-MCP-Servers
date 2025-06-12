# compute-server.py
import asyncio
import logging
import os
from typing import Any, Optional, Dict, List
import globus_compute_sdk
import globus_sdk

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

from globus_sdk.scopes import AuthScopes

from globus_compute_sdk.sdk.login_manager import AuthorizerLoginManager
from globus_compute_sdk.sdk.login_manager.manager import ComputeScopeBuilder


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("globus-compute-mcp")

# Global variables
compute_client: Optional[globus_compute_sdk.Client] = None
auth_client: Optional[globus_sdk.NativeAppAuthClient] = None
registered_functions: Dict[str, str] = {}

# Get client ID from environment
CLIENT_ID = os.getenv("GLOBUS_CLIENT_ID", "ee05bbfa-2a1a-4659-95df-ed8946e3aae6")

# Create server instance
server = Server("globus-compute-mcp")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="compute_authenticate",
            description="Authenticate with Globus Compute",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="complete_compute_auth",
            description="Complete authentication with auth code",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_code": {"type": "string", "description": "Authorization code"}
                },
                "required": ["auth_code"],
            },
        ),
        types.Tool(
            name="register_function",
            description="Register a Python function",
            inputSchema={
                "type": "object",
                "properties": {
                    "function_code": {
                        "type": "string",
                        "description": "Python function code",
                    },
                    "function_name": {"type": "string", "description": "Function name"},
                    "description": {
                        "type": "string",
                        "description": "Function description",
                    },
                },
                "required": ["function_code", "function_name"],
            },
        ),
        types.Tool(
            name="execute_function",
            description="Execute a registered function",
            inputSchema={
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "Function name"},
                    "endpoint_id": {"type": "string", "description": "Endpoint UUID"},
                    "function_args": {
                        "type": "array",
                        "description": "Function arguments",
                    },
                    "function_kwargs": {
                        "type": "object",
                        "description": "Function keyword arguments",
                    },
                },
                "required": ["function_name", "endpoint_id"],
            },
        ),
        types.Tool(
            name="check_task_status",
            description="Check task status",
            inputSchema={
                "type": "object",
                "properties": {"task_id": {"type": "string", "description": "Task ID"}},
                "required": ["task_id"],
            },
        ),
        types.Tool(
            name="get_task_result",
            description="Get task result",
            inputSchema={
                "type": "object",
                "properties": {"task_id": {"type": "string", "description": "Task ID"}},
                "required": ["task_id"],
            },
        ),
        types.Tool(
            name="list_registered_functions",
            description="List registered functions",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="create_hello_world",
            description="Create a hello world test function",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Handle tool calls"""
    try:
        if name == "compute_authenticate":
            result = await compute_authenticate()
        elif name == "complete_compute_auth":
            result = await complete_compute_auth(arguments["auth_code"])
        elif name == "register_function":
            result = await register_function(
                arguments["function_code"],
                arguments["function_name"],
                arguments.get("description", ""),
            )
        elif name == "execute_function":
            result = await execute_function(
                arguments["function_name"],
                arguments["endpoint_id"],
                arguments.get("function_args", []),
                arguments.get("function_kwargs", {}),
            )
        elif name == "check_task_status":
            result = await check_task_status(arguments["task_id"])
        elif name == "get_task_result":
            result = await get_task_result(arguments["task_id"])
        elif name == "list_registered_functions":
            result = await list_registered_functions()
        elif name == "create_hello_world":
            result = await create_hello_world()
        else:
            result = f"Unknown tool: {name}"

        return [types.TextContent(type="text", text=result)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


async def compute_authenticate() -> str:
    """Authenticate with Globus Compute"""
    global auth_client

    if CLIENT_ID == "YOUR_GLOBUS_CLIENT_ID":
        return "Please set GLOBUS_CLIENT_ID environment variable"

    try:
        auth_client = globus_sdk.NativeAppAuthClient(CLIENT_ID)
        auth_client.oauth2_start_flow(
            requested_scopes=[
                "https://auth.globus.org/scopes/facd7ccc-c5f4-42aa-916b-a0e270e2c2a9/all",
                "openid",
                "email",
                "profile",
            ]
        )

        authorize_url = auth_client.oauth2_get_authorize_url()

        return f"""Please visit this URL to authorize:

{authorize_url}

After authorization, use complete_compute_auth with the code."""

    except Exception as e:
        return f"Authentication failed: {str(e)}"


async def complete_compute_auth(auth_code: str) -> str:
    """Complete authentication"""
    global auth_client, compute_client

    if not auth_client:
        return "Please call compute_authenticate first"

    try:
        token_response = auth_client.oauth2_exchange_code_for_tokens(auth_code)

        ComputeScopes = ComputeScopeBuilder()

        compute_auth = globus_sdk.AccessTokenAuthorizer(
            token_response.by_resource_server["funcx_service"]["access_token"]
        )
        openid_auth = globus_sdk.AccessTokenAuthorizer(
            token_response.by_resource_server["auth.globus.org"]["access_token"]
        )

        compute_login_manager = AuthorizerLoginManager(
            authorizers={
                ComputeScopes.resource_server: compute_auth,
                AuthScopes.resource_server: openid_auth,
                "openid": openid_auth,
            }
        )
        compute_login_manager.ensure_logged_in()
        compute_client = globus_compute_sdk.Client(login_manager=compute_login_manager)

        return "Authentication completed successfully!"

    except Exception as e:
        return f"Authentication failed: {str(e)}"


async def register_function(
    function_code: str, function_name: str, description: str = ""
) -> str:
    """Register a function"""
    global registered_functions

    if not compute_client:
        return "Not authenticated. Please authenticate first."

    try:
        exec_globals = {}
        exec(function_code, exec_globals)

        functions = {
            k: v
            for k, v in exec_globals.items()
            if callable(v) and not k.startswith("_")
        }

        if not functions:
            return "No functions found in code"

        if len(functions) > 1:
            return f"Multiple functions found: {list(functions.keys())}. Use only one function."

        func_obj = list(functions.values())[0]
        func_uuid = compute_client.register_function(func_obj)
        registered_functions[function_name] = func_uuid

        return f"""Function registered successfully!

Name: {function_name}
UUID: {func_uuid}
Description: {description}

Code:
{function_code}"""

    except Exception as e:
        return f"Registration failed: {str(e)}"


async def execute_function(
    function_name: str, endpoint_id: str, function_args: tuple, function_kwargs: Dict,
) -> str:
    """Execute a function"""
    if not compute_client:
        return "Not authenticated"

    if function_name not in registered_functions:
        return f"Function not found. Available: {list(registered_functions.keys())}"

    try:
        func_uuid = registered_functions[function_name]

        task_id = compute_client.run(
            *function_args,
            function_id=func_uuid,
            endpoint_id=endpoint_id,
            **function_kwargs,
        )

        return f"""Function execution submitted!

Function: {function_name}
Endpoint: {endpoint_id}
Task ID: {task_id}
Arguments: {function_args}
Kwargs: {function_kwargs}

Use check_task_status to monitor progress."""

    except Exception as e:
        return f"Execution failed: {str(e)}"


async def check_task_status(task_id: str) -> str:
    """Check task status"""
    if not compute_client:
        return "Not authenticated"

    try:
        status = compute_client.get_task(task_id)

        return f"""Task Status:

Task ID: {task_id}
Status: {status}

Use get_task_result when status is 'success'."""

    except Exception as e:
        return f"Status check failed: {str(e)}"


async def get_task_result(task_id: str) -> str:
    """Get task result"""
    if not compute_client:
        return "Not authenticated"

    try:
        result = compute_client.get_result(task_id)

        return f"""Task Result:

Task ID: {task_id}
Result: {str(result)}
Type: {type(result).__name__}"""

    except Exception as e:
        return f"Failed to get result: {str(e)}"


async def list_registered_functions() -> str:
    """List registered functions"""
    if not registered_functions:
        return "No functions registered"

    result = "Registered Functions:\n\n"
    for name, uuid in registered_functions.items():
        result += f"{name}: {uuid}\n"

    return result


async def create_hello_world() -> str:
    """Create hello world function"""
    function_code = """def hello_compute(name="World"):
    import platform
    import os
    
    hostname = platform.node()
    username = os.getenv('USER', 'unknown')
    
    return f"Hello {name}! Running on {hostname} as {username}" """

    return await register_function(
        function_code.strip(), "hello_world", "Test function that returns system info"
    )


async def main():
    """Main server loop"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="globus-compute-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                    # notification=True,
                    # tools=True,
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
