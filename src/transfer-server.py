# globus_mcp_server.py
import asyncio
import logging
import os
from typing import Any, Optional, Sequence
import globus_sdk

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("globus-mcp")

# Global variables for Globus clients
transfer_client: Optional[globus_sdk.TransferClient] = None
auth_client: Optional[globus_sdk.NativeAppAuthClient] = None

# Get client ID from environment
CLIENT_ID = os.getenv("GLOBUS_CLIENT_ID", "ee05bbfa-2a1a-4659-95df-ed8946e3aae6")

# Create server instance
server = Server("globus-mcp")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available Globus tools"""
    return [
        types.Tool(
            name="globus_authenticate",
            description="Authenticate with Globus and get authorization URL",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="complete_globus_auth",
            description="Complete Globus authentication with authorization code",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_code": {
                        "type": "string",
                        "description": "Authorization code from Globus",
                    }
                },
                "required": ["auth_code"],
            },
        ),
        types.Tool(
            name="list_endpoints",
            description="List available Globus endpoints",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter_name": {
                        "type": "string",
                        "description": "Optional filter to search endpoints by name",
                    }
                },
            },
        ),
        types.Tool(
            name="submit_transfer",
            description="Submit a transfer job between two Globus endpoints",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_endpoint": {
                        "type": "string",
                        "description": "Source endpoint UUID",
                    },
                    "dest_endpoint": {
                        "type": "string",
                        "description": "Destination endpoint UUID",
                    },
                    "source_path": {
                        "type": "string",
                        "description": "Source file/directory path",
                    },
                    "dest_path": {
                        "type": "string",
                        "description": "Destination file/directory path",
                    },
                    "label": {
                        "type": "string",
                        "description": "Human-readable label for the transfer",
                    },
                },
                "required": [
                    "source_endpoint",
                    "dest_endpoint",
                    "source_path",
                    "dest_path",
                ],
            },
        ),
        types.Tool(
            name="check_transfer_status",
            description="Check the status of a Globus transfer job",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Transfer task ID to check",
                    }
                },
                "required": ["task_id"],
            },
        ),
        types.Tool(
            name="list_directory",
            description="List contents of a directory on a Globus endpoint",
            inputSchema={
                "type": "object",
                "properties": {
                    "endpoint_id": {
                        "type": "string",
                        "description": "Endpoint UUID to browse",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory path to list (default: /)",
                    },
                },
                "required": ["endpoint_id"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Handle tool calls"""

    if name == "globus_authenticate":
        return [types.TextContent(type="text", text=await globus_authenticate())]
    elif name == "complete_globus_auth":
        return [
            types.TextContent(
                type="text", text=await complete_globus_auth(arguments["auth_code"])
            )
        ]
    elif name == "list_endpoints":
        return [
            types.TextContent(
                type="text", text=await list_endpoints(arguments.get("filter_name", ""))
            )
        ]
    elif name == "submit_transfer":
        return [
            types.TextContent(
                type="text",
                text=await submit_transfer(
                    arguments["source_endpoint"],
                    arguments["dest_endpoint"],
                    arguments["source_path"],
                    arguments["dest_path"],
                    arguments.get("label", "MCP Transfer"),
                ),
            )
        ]
    elif name == "check_transfer_status":
        return [
            types.TextContent(
                type="text", text=await check_transfer_status(arguments["task_id"])
            )
        ]
    elif name == "list_directory":
        return [
            types.TextContent(
                type="text",
                text=await list_directory(
                    arguments["endpoint_id"], arguments.get("path", "/")
                ),
            )
        ]
    else:
        raise ValueError(f"Unknown tool: {name}")


async def globus_authenticate() -> str:
    """Authenticate with Globus and get authorization URL"""
    global auth_client

    if CLIENT_ID == "YOUR_GLOBUS_CLIENT_ID":
        return "❌ Please set your GLOBUS_CLIENT_ID environment variable."

    try:
        # Initialize the auth client
        auth_client = globus_sdk.NativeAppAuthClient(CLIENT_ID)

        # Request authorization
        auth_client.oauth2_start_flow(
            requested_scopes=["urn:globus:auth:scope:transfer.api.globus.org:all"]
        )

        # Get the authorization URL
        authorize_url = auth_client.oauth2_get_authorize_url()

        return f"""
🔐 **Globus Authentication Required**

Please visit this URL to authorize the application:

{authorize_url}

After authorization, you'll get an authorization code. 
Use the complete_globus_auth tool with that code to finish setup.
        """.strip()

    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return f"❌ Authentication failed: {str(e)}"


async def complete_globus_auth(auth_code: str) -> str:
    """Complete Globus authentication with the authorization code"""
    global auth_client, transfer_client

    if not auth_client:
        return "❌ Please call globus_authenticate first to start the auth flow."

    try:
        # Exchange the auth code for tokens
        token_response = auth_client.oauth2_exchange_code_for_tokens(auth_code)

        # Get the transfer token
        transfer_token = token_response.by_resource_server["transfer.api.globus.org"][
            "access_token"
        ]

        # Initialize the transfer client
        authorizer = globus_sdk.AccessTokenAuthorizer(transfer_token)
        transfer_client = globus_sdk.TransferClient(authorizer=authorizer)

        return "✅ **Authentication completed successfully!** You can now use all Globus transfer functions."

    except Exception as e:
        logger.error(f"Token exchange error: {e}")
        return f"❌ Authentication completion failed: {str(e)}"


async def list_endpoints(filter_name: str = "") -> str:
    """List available Globus endpoints"""
    if not transfer_client:
        return "❌ Not authenticated. Please run globus_authenticate first."

    try:
        # Get endpoints
        search_filter = filter_name if filter_name else None
        endpoints = transfer_client.endpoint_search(filter_fulltext=search_filter)

        if not endpoints.data:
            return "No endpoints found matching your criteria."

        result = "📡 **Available Endpoints:**\n\n"
        for ep in endpoints.data[:10]:  # Limit to first 10 results
            result += f"**{ep['display_name']}**\n"
            result += f"   📋 ID: `{ep['id']}`\n"
            result += f"   👤 Owner: {ep['owner_string']}\n"
            result += f"   📝 Description: {ep.get('description', 'N/A')}\n"
            result += f"   🔌 Type: {ep.get('entity_type', 'Unknown')}\n"
            result += "-" * 60 + "\n"

        if len(endpoints.data) > 10:
            result += f"\n... and {len(endpoints.data) - 10} more endpoints. Use filter_name to narrow results."

        return result

    except Exception as e:
        logger.error(f"Error listing endpoints: {e}")
        return f"❌ Failed to list endpoints: {str(e)}"


async def submit_transfer(
    source_endpoint: str,
    dest_endpoint: str,
    source_path: str,
    dest_path: str,
    label: str = "MCP Transfer",
) -> str:
    """Submit a transfer job between two Globus endpoints"""
    if not transfer_client:
        return "❌ Not authenticated. Please run globus_authenticate first."

    try:
        # Create transfer data
        transfer_data = globus_sdk.TransferData(
            source_endpoint=source_endpoint,
            destination_endpoint=dest_endpoint,
            label=label,
        )

        # Add transfer item
        transfer_data.add_item(source_path=source_path, destination_path=dest_path)

        # Submit the transfer
        result = transfer_client.submit_transfer(transfer_data)

        return f"""
🚀 **Transfer Submitted Successfully!**

📋 **Task ID:** `{result['task_id']}`
📊 **Status:** {result['message']}
🏷️ **Label:** {label}
📁 **Source:** `{source_path}` on `{source_endpoint}`
📁 **Destination:** `{dest_path}` on `{dest_endpoint}`

Use check_transfer_status with the Task ID to monitor progress.
        """.strip()

    except Exception as e:
        logger.error(f"Transfer submission error: {e}")
        return f"❌ Transfer submission failed: {str(e)}"


async def check_transfer_status(task_id: str) -> str:
    """Check the status of a Globus transfer job"""
    if not transfer_client:
        return "❌ Not authenticated. Please run globus_authenticate first."

    try:
        # Get task status
        task = transfer_client.get_task(task_id)

        # Format status with emoji
        status_emoji = {
            "ACTIVE": "🔄",
            "SUCCEEDED": "✅",
            "FAILED": "❌",
            "INACTIVE": "⏸️",
        }.get(task["status"], "❓")

        result = f"""
{status_emoji} **Transfer Status Report**

📋 **Task ID:** `{task['task_id']}`
📊 **Status:** {task['status']}
🏷️ **Label:** {task['label']}
📁 **Files Transferred:** {task.get('files_transferred', 0)}
📊 **Bytes Transferred:** {task.get('bytes_transferred', 0):,} bytes
🎯 **Source:** {task.get('source_endpoint_display_name', 'Unknown')}
🎯 **Destination:** {task.get('destination_endpoint_display_name', 'Unknown')}
⏰ **Submitted:** {task.get('request_time', 'N/A')}
⏰ **Completed:** {task.get('completion_time', 'In Progress' if task['status'] == 'ACTIVE' else 'N/A')}
        """.strip()

        if task["status"] == "FAILED":
            result += f"\n\n❌ **Error Details:** {task.get('nice_status_details', 'Unknown error')}"
        elif task["status"] == "ACTIVE":
            result += (
                f"\n\n🔄 **Progress:** Transfer is currently active and processing..."
            )

        return result

    except Exception as e:
        logger.error(f"Status check error: {e}")
        return f"❌ Failed to check transfer status: {str(e)}"


async def list_directory(endpoint_id: str, path: str = "/") -> str:
    """List contents of a directory on a Globus endpoint"""
    if not transfer_client:
        return "❌ Not authenticated. Please run globus_authenticate first."

    try:
        # List directory contents
        response = transfer_client.operation_ls(endpoint_id, path=path)

        if not response.data:
            return f"📁 Directory `{path}` is empty or inaccessible."

        result = f"📁 **Directory listing for `{path}`**\n"
        result += f"🎯 **Endpoint:** `{endpoint_id}`\n\n"

        # Sort: directories first, then files
        items = sorted(
            response.data, key=lambda x: (x["type"] != "dir", x["name"].lower())
        )

        for item in items[:50]:  # Limit to 50 items
            icon = "📁" if item["type"] == "dir" else "📄"
            size = f" ({item['size']:,} bytes)" if item.get("size") else ""
            modified = (
                f" - {item['last_modified']}" if item.get("last_modified") else ""
            )
            result += f"{icon} `{item['name']}`{size}{modified}\n"

        if len(response.data) > 50:
            result += f"\n... and {len(response.data) - 50} more items."

        return result

    except Exception as e:
        logger.error(f"Directory listing error: {e}")
        return f"❌ Failed to list directory: {str(e)}"


async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="globus-mcp",
                server_version="0.2.0",
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
