#!/usr/bin/env python3
"""
NERSC Status MCP Server

This MCP server provides tools to check the status of NERSC (National Energy Research Scientific Computing Center) systems.
It retrieves information from NERSC's public API about system availability, maintenance, and other status updates.
"""

import asyncio
import json
import logging
from typing import Any, Sequence
from urllib.parse import urljoin

import aiohttp
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nersc-status")

# NERSC API Configuration
NERSC_API_BASE = "https://api.nersc.gov/api/v1.2/"
NERSC_STATUS_ENDPOINT = "status/"

class NERSCStatusServer:
    def __init__(self):
        self.server = Server("nersc-status")
        self.session = None
        self.setup_handlers()

    def setup_handlers(self):
        @self.server.list_resources()
        async def list_resources() -> list[Resource]:
            """List available NERSC status resources."""
            return [
                Resource(
                    uri="nersc://status/systems",
                    name="NERSC System Status",
                    description="Current status of all NERSC computing systems",
                    mimeType="application/json",
                ),
                Resource(
                    uri="nersc://status/summary",
                    name="NERSC Status Summary",
                    description="Summary of NERSC system availability",
                    mimeType="text/plain",
                ),
            ]

        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read NERSC status resources."""
            if uri == "nersc://status/systems":
                status_data = await self._get_system_status()
                return json.dumps(status_data, indent=2)
            elif uri == "nersc://status/summary":
                status_data = await self._get_system_status()
                return self._format_status_summary(status_data)
            else:
                raise Exception(f"Unknown resource: {uri}")

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available NERSC status tools."""
            return [
                Tool(
                    name="get_nersc_status",
                    description="Get the current status of NERSC computing systems",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "system": {
                                "type": "string",
                                "description": "Specific system to check (optional). If not provided, returns all systems.",
                                "enum": ["perlmutter", "cori", "spin", "jupyter", "global_homes", "community_file_system"]
                            },
                            "format": {
                                "type": "string",
                                "description": "Output format: 'json' for detailed data or 'summary' for human-readable text",
                                "enum": ["json", "summary"],
                                "default": "summary"
                            }
                        },
                        "additionalProperties": False
                    },
                ),
                Tool(
                    name="check_system_availability",
                    description="Check if a specific NERSC system is available for use",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "system": {
                                "type": "string",
                                "description": "Name of the system to check",
                                "enum": ["perlmutter", "cori", "spin", "jupyter", "global_homes", "community_file_system"]
                            }
                        },
                        "required": ["system"],
                        "additionalProperties": False
                    },
                ),
                Tool(
                    name="get_maintenance_info",
                    description="Get information about scheduled maintenance and outages",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "system": {
                                "type": "string",
                                "description": "Specific system to check for maintenance (optional)",
                                "enum": ["perlmutter", "cori", "spin", "jupyter", "global_homes", "community_file_system"]
                            }
                        },
                        "additionalProperties": False
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Handle tool calls for NERSC status operations."""
            try:
                if name == "get_nersc_status":
                    return await self._handle_get_status(arguments)
                elif name == "check_system_availability":
                    return await self._handle_check_availability(arguments)
                elif name == "get_maintenance_info":
                    return await self._handle_get_maintenance(arguments)
                else:
                    raise Exception(ErrorCode.METHOD_NOT_FOUND, f"Unknown tool: {name}")
            except Exception as e:
                logger.error(f"Error in tool {name}: {str(e)}")
                raise Exception(f"Tool execution failed: {str(e)}")

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _get_system_status(self) -> dict:
        """Retrieve system status from NERSC API."""
        session = await self._get_http_session()
        url = urljoin(NERSC_API_BASE, NERSC_STATUS_ENDPOINT)
        
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(
                        
                        f"NERSC API returned status {response.status}: {await response.text()}"
                    )
        except aiohttp.ClientError as e:
            raise Exception(f"Failed to connect to NERSC API: {str(e)}")

    def _format_status_summary(self, status_data: dict) -> str:
        """Format status data into a human-readable summary."""
        summary = ["NERSC System Status Summary", "=" * 30, ""]
        
        if not status_data:
            return "No status data available from NERSC API."
        
        # Handle different possible API response formats
        systems = status_data
        if isinstance(status_data, dict) and 'systems' in status_data:
            systems = status_data['systems']
        
        for system_name, system_info in systems.items():
            if isinstance(system_info, dict):
                status = system_info.get('status', 'Unknown')
                description = system_info.get('description', 'No description available')
                
                # Format system name
                formatted_name = system_name.replace('_', ' ').title()
                summary.append(f"🖥️  {formatted_name}:")
                
                # Status indicator
                if status.lower() in ['active', 'available', 'up']:
                    summary.append(f"   Status: ✅ {status}")
                elif status.lower() in ['degraded', 'limited']:
                    summary.append(f"   Status: ⚠️  {status}")
                else:
                    summary.append(f"   Status: ❌ {status}")
                
                # Additional info
                if description and description != status:
                    summary.append(f"   Info: {description}")
                
                # Check for maintenance info
                if 'maintenance' in system_info:
                    maintenance = system_info['maintenance']
                    if maintenance:
                        summary.append(f"   Maintenance: {maintenance}")
                
                # Check for updated timestamp
                if 'updated' in system_info:
                    summary.append(f"   Last Updated: {system_info['updated']}")
                
                summary.append("")
        
        return "\n".join(summary)

    async def _handle_get_status(self, arguments: dict) -> list[TextContent]:
        """Handle get_nersc_status tool call."""
        status_data = await self._get_system_status()
        format_type = arguments.get('format', 'summary')
        specific_system = arguments.get('system')
        
        if specific_system and specific_system in status_data:
            status_data = {specific_system: status_data[specific_system]}
        elif specific_system:
            return [TextContent(
                type="text",
                text=f"System '{specific_system}' not found in NERSC status data."
            )]
        
        if format_type == 'json':
            result = json.dumps(status_data, indent=2)
        else:
            result = self._format_status_summary(status_data)
        
        return [TextContent(type="text", text=result)]

    async def _handle_check_availability(self, arguments: dict) -> list[TextContent]:
        """Handle check_system_availability tool call."""
        system = arguments['system']
        status_data = await self._get_system_status()
        
        if system not in status_data:
            return [TextContent(
                type="text",
                text=f"❌ System '{system}' not found in NERSC status data."
            )]
        
        system_info = status_data[system]
        status = system_info.get('status', 'Unknown')
        description = system_info.get('description', '')
        
        # Determine availability
        if status.lower() in ['active', 'available', 'up']:
            availability_text = f"✅ {system.replace('_', ' ').title()} is AVAILABLE"
        elif status.lower() in ['degraded', 'limited']:
            availability_text = f"⚠️  {system.replace('_', ' ').title()} is PARTIALLY AVAILABLE"
        else:
            availability_text = f"❌ {system.replace('_', ' ').title()} is UNAVAILABLE"
        
        result = [availability_text]
        result.append(f"Status: {status}")
        
        if description and description != status:
            result.append(f"Details: {description}")
        
        return [TextContent(type="text", text="\n".join(result))]

    async def _handle_get_maintenance(self, arguments: dict) -> list[TextContent]:
        """Handle get_maintenance_info tool call."""
        status_data = await self._get_system_status()
        specific_system = arguments.get('system')
        
        maintenance_info = []
        systems_to_check = [specific_system] if specific_system else status_data.keys()
        
        for system_name in systems_to_check:
            if system_name not in status_data:
                continue
                
            system_info = status_data[system_name]
            formatted_name = system_name.replace('_', ' ').title()
            
            # Check for maintenance-related information
            has_maintenance = False
            
            # Check status for maintenance indicators
            status = system_info.get('status', '').lower()
            if 'maintenance' in status or 'maint' in status:
                maintenance_info.append(f"🔧 {formatted_name}: Currently under maintenance")
                maintenance_info.append(f"   Status: {system_info.get('status', 'Unknown')}")
                has_maintenance = True
            
            # Check description for maintenance info
            description = system_info.get('description', '').lower()
            if 'maintenance' in description or 'maint' in description:
                maintenance_info.append(f"🔧 {formatted_name}: Maintenance information available")
                maintenance_info.append(f"   Details: {system_info.get('description', '')}")
                has_maintenance = True
            
            # Check for explicit maintenance field
            if 'maintenance' in system_info and system_info['maintenance']:
                maintenance_info.append(f"🔧 {formatted_name}: Scheduled maintenance")
                maintenance_info.append(f"   Info: {system_info['maintenance']}")
                has_maintenance = True
            
            # If no maintenance info found but system is down, mention it
            if not has_maintenance and status in ['down', 'unavailable', 'offline']:
                maintenance_info.append(f"❌ {formatted_name}: Currently unavailable (may be under maintenance)")
                maintenance_info.append(f"   Status: {system_info.get('status', 'Unknown')}")
        
        if not maintenance_info:
            if specific_system:
                result = f"No maintenance information found for {specific_system.replace('_', ' ').title()}."
            else:
                result = "No current maintenance activities found for NERSC systems."
        else:
            result = "NERSC Maintenance Information:\n" + "\n".join(maintenance_info)
        
        return [TextContent(type="text", text=result)]

    async def cleanup(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()

async def main():
    """Main entry point for the NERSC Status MCP server."""
    nersc_server = NERSCStatusServer()
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            await nersc_server.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="nersc-status",
                    server_version="1.0.0",
                    capabilities=nersc_server.server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={},
                    ),
                ),
            )
    finally:
        await nersc_server.cleanup()

if __name__ == "__main__":
    asyncio.run(main())