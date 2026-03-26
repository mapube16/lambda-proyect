"""
Hive Agent Orchestrator
Manages OpenAI Swarm-style agents with real-time state broadcasting
"""
import asyncio
import json
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from openai import OpenAI
from models import Agent, AgentState, AgentRole, AgentUpdate


class HiveOrchestrator:
    def __init__(self, openai_api_key: str):
        try:
            if openai_api_key:
                self.client = OpenAI(api_key=openai_api_key)
            else:
                self.client = None
        except Exception as e:
            print(f"Warning: Failed to initialize OpenAI client: {e}")
            self.client = None
        self.agents: Dict[str, Agent] = {}
        self.conversations: Dict[str, List[dict]] = {}
        self.broadcast_callback: Optional[Callable] = None
        self._palette_counter = 0
        
        # Default tools available to all agents
        self.default_tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to read"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write content to a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to write"},
                            "content": {"type": "string", "description": "Content to write"}
                        },
                        "required": ["path", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_code",
                    "description": "Execute Python code",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "Python code to execute"}
                        },
                        "required": ["code"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delegate_task",
                    "description": "Delegate a subtask to another agent",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_role": {"type": "string", "enum": ["coder", "researcher", "writer", "reviewer"]},
                            "task": {"type": "string", "description": "Task description for the sub-agent"}
                        },
                        "required": ["agent_role", "task"]
                    }
                }
            }
        ]
    
    def set_broadcast_callback(self, callback: Callable):
        """Set callback for broadcasting state updates via WebSocket"""
        self.broadcast_callback = callback
    
    async def broadcast_update(self, update: AgentUpdate):
        """Broadcast agent state update to all connected clients"""
        if self.broadcast_callback:
            await self.broadcast_callback(update.model_dump())
    
    def _get_next_palette(self) -> int:
        """Cycle through available character palettes (0-5)"""
        palette = self._palette_counter % 6
        self._palette_counter += 1
        return palette
    
    def _get_system_prompt(self, role: AgentRole, custom_instructions: Optional[str] = None) -> str:
        """Generate system prompt based on agent role"""
        role_prompts = {
            AgentRole.CODER: "You are an expert software developer. Write clean, efficient code.",
            AgentRole.RESEARCHER: "You are a research specialist. Find and synthesize information.",
            AgentRole.WRITER: "You are a technical writer. Create clear documentation.",
            AgentRole.REVIEWER: "You are a code reviewer. Analyze code for bugs and improvements.",
            AgentRole.PLANNER: "You are a project planner. Break down tasks and coordinate work."
        }
        
        base = role_prompts.get(role, "You are a helpful AI assistant.")
        if custom_instructions:
            base += f"\n\nAdditional instructions: {custom_instructions}"
        return base
    
    async def create_agent(
        self, 
        name: str, 
        role: AgentRole,
        instructions: Optional[str] = None,
        parent_id: Optional[str] = None
    ) -> Agent:
        """Create a new agent"""
        import uuid
        agent_id = str(uuid.uuid4())[:8]
        
        agent = Agent(
            id=agent_id,
            name=name,
            role=role,
            palette=self._get_next_palette(),
            is_subagent=parent_id is not None,
            parent_agent_id=parent_id
        )
        
        self.agents[agent_id] = agent
        self.conversations[agent_id] = [
            {"role": "system", "content": self._get_system_prompt(role, instructions)}
        ]
        
        return agent
    
    async def update_agent_state(
        self, 
        agent_id: str, 
        state: AgentState,
        tool: Optional[str] = None,
        tool_status: Optional[str] = None
    ):
        """Update agent state and broadcast to clients"""
        if agent_id not in self.agents:
            return
        
        agent = self.agents[agent_id]
        agent.state = state
        agent.current_tool = tool
        agent.tool_status = tool_status
        
        await self.broadcast_update(AgentUpdate(
            agent_id=agent_id,
            state=state,
            current_tool=tool,
            tool_status=tool_status
        ))
    
    async def execute_tool(self, agent_id: str, tool_name: str, arguments: dict) -> str:
        """Execute a tool and return result (mock implementation)"""
        await self.update_agent_state(
            agent_id, 
            AgentState.TOOL_USE, 
            tool_name,
            f"Executing {tool_name}..."
        )
        
        # Simulate tool execution time
        await asyncio.sleep(1.5)
        
        # Mock tool results
        if tool_name == "read_file":
            result = f"Contents of {arguments.get('path', 'file')}: [mock file contents]"
        elif tool_name == "write_file":
            result = f"Successfully wrote to {arguments.get('path', 'file')}"
        elif tool_name == "search_web":
            result = f"Search results for '{arguments.get('query', '')}': [mock results]"
        elif tool_name == "run_code":
            result = "Code executed successfully. Output: [mock output]"
        elif tool_name == "delegate_task":
            # Create sub-agent
            sub_role = AgentRole(arguments.get("agent_role", "coder"))
            sub_agent = await self.create_agent(
                name=f"Sub-{sub_role.value}",
                role=sub_role,
                parent_id=agent_id
            )
            result = f"Delegated task to sub-agent {sub_agent.id}"
        else:
            result = f"Tool {tool_name} executed"
        
        return result
    
    async def run_agent(self, agent_id: str, user_message: str) -> str:
        """Run agent with a user message, handling tool calls"""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        agent = self.agents[agent_id]
        conversation = self.conversations[agent_id]
        
        # Add user message
        conversation.append({"role": "user", "content": user_message})
        
        # Update state to thinking
        await self.update_agent_state(agent_id, AgentState.THINKING)
        
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            try:
                response = self.client.chat.completions.create(
                    model="gpt-5.4-2026-03-05",
                    messages=conversation,
                    tools=self.default_tools,
                    tool_choice="auto"
                )
            except Exception as e:
                await self.update_agent_state(agent_id, AgentState.ERROR, tool_status=str(e))
                raise
            
            message = response.choices[0].message
            conversation.append(message.model_dump())
            
            # Check for tool calls
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    # Execute tool
                    result = await self.execute_tool(agent_id, tool_name, arguments)
                    
                    # Add tool result to conversation
                    conversation.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })
            else:
                # No more tool calls, agent is done
                await self.update_agent_state(agent_id, AgentState.WAITING)
                return message.content or ""
        
        # Max iterations reached
        await self.update_agent_state(agent_id, AgentState.WAITING)
        return "Max iterations reached"
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self.agents.get(agent_id)
    
    def get_all_agents(self) -> List[Agent]:
        return list(self.agents.values())
    
    async def remove_agent(self, agent_id: str):
        """Remove an agent"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            if agent_id in self.conversations:
                del self.conversations[agent_id]
