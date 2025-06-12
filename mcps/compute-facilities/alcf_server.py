#!/usr/bin/env python3
"""
MCP Server for ALCF System Status Monitoring
Monitors Polaris cluster status by checking job activity.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
import aiohttp
from datetime import datetime

# MCP SDK imports
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alcf-status-mcp")

class ALCFStatusMCP:
    def __init__(self):
        self.server = Server("alcf-status-mcp")
        self.alcf_status_url = "https://status.alcf.anl.gov/polaris/activity.json"
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register MCP handlers"""
        
        @self.server.list_resources()
        async def handle_list_resources() -> List[Resource]:
            """List available resources"""
            return [
                Resource(
                    uri="alcf://polaris/status",
                    name="Polaris System Status",
                    description="Current system status of ALCF Polaris cluster",
                    mimeType="application/json"
                ),
                Resource(
                    uri="alcf://polaris/jobs",
                    name="Polaris Job Activity",
                    description="Current job activity on ALCF Polaris cluster",
                    mimeType="application/json"
                )
            ]
        
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """Read resource content"""
            if uri == "alcf://polaris/status":
                status = await self._get_system_status()
                return json.dumps(status, indent=2)
            elif uri == "alcf://polaris/jobs":
                jobs = await self._get_job_activity()
                return json.dumps(jobs, indent=2)
            else:
                raise ValueError(f"Unknown resource: {uri}")
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            """List available tools"""
            return [
                Tool(
                    name="check_alcf_status",
                    description="Check the current system status of ALCF Polaris cluster",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "detailed": {
                                "type": "boolean",
                                "description": "Whether to return detailed job information",
                                "default": False
                            }
                        }
                    }
                ),
                Tool(
                    name="get_running_jobs",
                    description="Get information about currently running jobs on Polaris",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of running jobs to return",
                                "default": 10
                            }
                        }
                    }
                ),
                Tool(
                    name="system_health_summary",
                    description="Get a summary of system health based on job activity",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls"""
            if name == "check_alcf_status":
                detailed = arguments.get("detailed", False)
                result = await self._check_alcf_status(detailed)
                return [TextContent(type="text", text=result)]
            
            elif name == "get_running_jobs":
                limit = arguments.get("limit", 10)
                result = await self._get_running_jobs(limit)
                return [TextContent(type="text", text=result)]
            
            elif name == "system_health_summary":
                result = await self._get_system_health_summary()
                return [TextContent(type="text", text=result)]
            
            else:
                raise ValueError(f"Unknown tool: {name}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def _fetch_activity_data(self) -> Dict[str, Any]:
        """Fetch activity data from ALCF status endpoint"""
        session = await self._get_session()
        
        try:
            async with session.get(self.alcf_status_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    raise Exception(f"HTTP {response.status}: {await response.text()}")
        except Exception as e:
            logger.error(f"Error fetching ALCF status: {e}")
            raise
    
    async def _get_system_status(self) -> Dict[str, Any]:
        """Get system status information"""
        try:
            data = await self._fetch_activity_data()
            
            # Analyze the data to determine system status
            running_jobs = data.get("running", [])
            starting_jobs = data.get("starting", [])
            queued_jobs = data.get("queued", [])
            total_jobs = len(running_jobs) + len(queued_jobs) + len(starting_jobs)

            status = {
                "timestamp": datetime.now().isoformat(),
                "system_operational": len(running_jobs) > 0,
                "total_jobs": total_jobs,
                "running_jobs": len(running_jobs),
                "starting_jobs": len(starting_jobs),
                "queued_jobs": len(queued_jobs),
                "status_summary": "Operational" if len(running_jobs) > 0 else "No running jobs detected"
            }
            
            return status
            
        except Exception as e:
            return {
                "timestamp": datetime.now().isoformat(),
                "system_operational": False,
                "error": str(e),
                "status_summary": "Error retrieving status"
            }
    
    async def _get_job_activity(self) -> Dict[str, Any]:
        """Get detailed job activity"""
        try:
            data = await self._fetch_activity_data()
            return data
        except Exception as e:
            return {"error": str(e)}
    
    async def _check_alcf_status(self, detailed: bool = False) -> str:
        """Check ALCF system status"""
        try:
            data = await self._fetch_activity_data()
            running_jobs = data.get("running", [])
            starting_jobs = data.get("starting", [])
            queued_jobs = data.get("queued", [])
            
            total_jobs = len(running_jobs) + len(queued_jobs) + len(starting_jobs)
            
            if total_jobs == 0:
                return "⚠️  ALCF Polaris Status: No job data available"
            
            # Generate status report
            status_lines = [
                f"🖥️  ALCF Polaris System Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                "=" * 60
            ]
            
            if running_jobs:
                status_lines.append(f"✅ System Status: OPERATIONAL ({len(running_jobs)} jobs running)")
            else:
                status_lines.append("❌ System Status: NO RUNNING JOBS")
            
            status_lines.append(f"📊 Total Jobs: {total_jobs}")
            
            # Job state breakdown
            status_lines.append("\n📋 Job State Summary:")
            status_lines.append(f"   🟢 RUNNING: {len(running_jobs)}")
            status_lines.append(f"   🔵 QUEUED: {len(queued_jobs)}")
            status_lines.append(f"   ⚪ STARTING: {len(starting_jobs)}")
            
            if detailed and running_jobs:
                status_lines.append(f"\n🏃 Running Jobs Details:")
                for i, job in enumerate(running_jobs[:10]):  # Limit to first 10
                    job_id = job.get("jobid", "unknown")
                    project = job.get("project", "unknown")
                    nodes = job.get("location", "unknown")
                    queue = job.get("queue", "unknown")
                    status_lines.append(f"   {i+1}. Job {job_id} | Project: {project} | Queue: {queue} | Nodes: {nodes}")
                
                if len(running_jobs) > 10:
                    status_lines.append(f"   ... and {len(running_jobs) - 10} more")
            
            return "\n".join(status_lines)
            
        except Exception as e:
            return f"❌ Error checking ALCF status: {str(e)}"
    
    async def _get_running_jobs(self, limit: int = 10) -> str:
        """Get information about running jobs"""
        try:
            data = await self._fetch_activity_data()
            running_jobs = data.get("running", [])
            
            if not running_jobs:
                return "📋 No running jobs found on ALCF Polaris"
            
            result_lines = [
                f"🏃 Running Jobs on ALCF Polaris ({len(running_jobs)} total)",
                "=" * 50
            ]
            
            for i, job in enumerate(running_jobs[:limit]):
                job_id = job.get("jobid", "N/A")
                project = job.get("project", "N/A")
                nodes = job.get("location", "N/A")
                queue = job.get("queue", "N/A")
                start_time = job.get("starttime", "N/A")
                
                result_lines.append(f"\n🔹 Job #{i+1}")
                result_lines.append(f"   Job ID: {job_id}")
                result_lines.append(f"   Project: {project}")
                result_lines.append(f"   Nodes: {nodes}")
                result_lines.append(f"   Queue: {queue}")
                result_lines.append(f"   Start Time: {start_time}")
            
            if len(running_jobs) > limit:
                result_lines.append(f"\n... and {len(running_jobs) - limit} more running jobs")
            
            return "\n".join(result_lines)
            
        except Exception as e:
            return f"❌ Error retrieving running jobs: {str(e)}"
    
    async def _get_system_health_summary(self) -> str:
        """Get system health summary"""
        try:
            data = await self._fetch_activity_data()
            running_jobs = data.get("running", [])
            starting_jobs = data.get("starting", [])
            queued_jobs = data.get("queued", [])
            
            total_jobs = len(running_jobs) + len(queued_jobs) + len(starting_jobs)
            
            if not jobs:
                return "⚠️  System Health: Unable to determine - No job data available"
            
            # Calculate health metrics
            
            # Determine health status
            if running_jobs > 0:
                health_status = "HEALTHY"
                emoji = "💚"
            elif queued_jobs > 0:
                health_status = "IDLE"
                emoji = "💛"
            else:
                health_status = "INACTIVE"
                emoji = "❤️"
            
            summary_lines = [
                f"{emoji} ALCF Polaris System Health Summary",
                "=" * 40,
                f"Overall Status: {health_status}",
                f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                "",
                f"📊 Job Statistics:",
                f"   • Total Jobs: {total_jobs}",
                f"   • Running: {running_jobs}",
                f"   • Queued: {queued_jobs}",
                "",
                f"🎯 Jobs running: {(running_jobs / max(total_jobs, 1)) * 100:.1f}%"
            ]
            
            # Add recommendations
            if running_jobs == 0 and queued_jobs > 0:
                summary_lines.append("\n💡 Note: Jobs are queued but none are running. System may be in maintenance or experiencing issues.")
            elif running_jobs == 0 and queued_jobs == 0:
                summary_lines.append("\n💡 Note: No active job activity detected. System may be offline or in maintenance.")
            
            return "\n".join(summary_lines)
            
        except Exception as e:
            return f"❌ Error generating health summary: {str(e)}"
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
    
    async def run(self):
        """Run the MCP server"""
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="alcf-status-mcp",
                        server_version="1.0.0",
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={},
                            # notification=True,
                            # experimental={}
                        )
                    )
                )
        finally:
            await self.cleanup()

async def main():
    """Main entry point"""
    mcp = ALCFStatusMCP()
    await mcp.run()

if __name__ == "__main__":
    asyncio.run(main())