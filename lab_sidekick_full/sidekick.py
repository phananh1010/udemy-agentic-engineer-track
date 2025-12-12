from typing import Annotated
from typing import List, Any, Optional, Dict
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from pydantic import BaseModel, Field

from sidekick_tools import playwright_tools, other_tools

import uuid
import asyncio
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(override=True)


class State(TypedDict):
    messages: Annotated[List[Any], add_messages]
    success_criteria: str
    feedback_on_work: Optional[str]
    success_criteria_met: bool
    user_input_needed: bool


class EvaluatorOutput(BaseModel):
    feedback: str = Field(description="Feedback on the assistant's response")
    success_criteria_met: bool = Field(description="Whether the success criteria have been met")
    user_input_needed: bool = Field(
        description="True if more input is needed from the user, or clarifications, or the assistant is stuck"
    )

class Sidekick:
    def __init__(self):
        self.worker_llm_with_tools = None    #node
        self.evaluator_llm_with_tools = None
        self.worker_tools = None
        self.llm_with_worker_tools = None
        self.evaluator_tools = None
        self.graph = None
        self.sidekick_id = str(uuid.uuid4())
        self.memory = MemorySaver()
        self.browser = None
        self.playwright = None

    async def setup(self):
        # define tools
        playwright_future = playwright_tools()
        other_future = other_tools()
        (self.tools, self.browser, self.playwright), self.other_tools = await asyncio.gather(
                                                            playwright_future,
                                                            other_future,
                                                            )
        self.tools += self.other_tools
        # defines llm with tool binding
        llm_worker = ChatOpenAI(model="gpt-4o-mini")
        self.llm_with_worker_tools = llm_worker.bind_tools(self.tools)
        llm_evaluator = ChatOpenAI(model="gpt-4o-mini")
        self.llm_with_evaluator_output = llm_evaluator.with_structured_output(EvaluatorOutput)

        #build graph
        await self.build_graph()

    def worker(self, state: State) -> Dict[str, Any]:
        """processing logic of the worker node"""
        system_message = f"""You are a helpful assistant that use tools to complete tasks.
Keep working on task until you have questions or clarification from users or success criteria are met.
Success criteria:
{state["success_criteria"]}
Reply either with a question or with your final response.
If question, clearly state the question. Example: please clarify for <the unclear thing> is either <option 1> or <option 2> or <option 3> etc...
If finished, final response should not be a question.
"""
    
        if state.get("feedback_on_work"):
            system_message = f"""
Your previous reply is incomplete and rejected. Here is the feedback: 
{state['feedback_on_work']}
Use this feedback to continue the assignment, verify if success criteria is met or question to users is required.
"""
        found_system_message = False
        messages = state["messages"]
        for message in messages:
            if isinstance(message, SystemMessage):
                found_system_message = True
        # we only append system message once, should be at the first time this worker is invoked
        if not found_system_message: 
            messages = [SystemMessage(content=system_message)] + messages
        #why processing task receive raw HumanMesage and AIMessage class
        response = self.llm_with_worker_tools.invoke(messages) # -> No worries, langchain automatically extract {"role": ..., "content": ...} as input to LLM. https://docs.langchain.com/oss/python/langchain/models
        #response here should have tool_calls key if they decide to invoke
    
        return {"messages": [response]}

    def worker_router(self, state:State) -> str:
        """custom made tool routing function for conditional edge in langgraph"""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls: #note: last_message maybe HumanMessage or AIMessage, not a dict
            return "tools"
        else:
            return "evaluator"

    def format_conversation(self, messages: List[Any]) -> str:
        conversation = "Conversation history: \n\n"
        for message in messages:
            if isinstance(message, HumanMessage):
                conversation += f"User: {message.content}\n"
            elif isinstance(message, AIMessage):
                text = message.content or "[Tools use]"
                conversation += f"Assistant: {text}\n"
        return conversation  #but here we only get content

    def evaluator(self, state: State) -> State:
        last_response = state["messages"][-1].content
    
        system_message = """You are strict and succint evaluator who determines if a task is completed successfully by an Assistant or not.
Assess the Assistant's last response, and provide feedback and decision whether the success criteria has been met.
"""
        user_message = f"""You are evaluating a conversation between the User and Assistant.
Conversation history with assistant, starting with user original request is:
{self.format_conversation(state["messages"])}

Success criteria for this assignment:
{state["success_criteria"]}

Final response from the Assistant for evaluation:
{last_response}

Now, begin evaluating.
"""
        if state["feedback_on_work"]: 
            user_message += f"Also, in previous attempt from the Assistant, you provided feedback: {state['feedback_on_work']}\n"
            user_message += f"If assistant repeat the mistakes, consider responding that user input is required.\n"
    
        evaluator_message = [SystemMessage(content=system_message), HumanMessage(content=user_message)]
    
        eval_result = self.llm_with_evaluator_output.invoke(evaluator_message)# unreliable tool calling here, method="json_mode", include_raw=False)
        new_state = { 
            #message include information that also attached to the state
            "messages": [{"role": "assistant", "content": f"Evaluator's feedback on this answer: {eval_result.feedback}"}],
            "feedback_on_work": eval_result.feedback,
            "success_criteria_met": eval_result.success_criteria_met,
            "user_input_needed": eval_result.user_input_needed
        }
        return new_state

    def evaluator_router(self, state: State) -> str:
        """Evaluator router, used on conditional edge on langgraph, Nope, maybe it as there is no tool call, but may be still condition to worker node"""
        if state['success_criteria_met'] or state['user_input_needed']:
            return "END" # ok criteria, ready to answer, or need to double check
        else:
            return "worker"

        
    async def build_graph(self):
        graph_builder = StateGraph(State)

        graph_builder.add_node("worker", self.worker)
        graph_builder.add_node("tools", ToolNode(self.tools))
        graph_builder.add_node("evaluator", self.evaluator)

        graph_builder.add_edge(START, "worker")
        graph_builder.add_conditional_edges("worker", self.worker_router, {"tools": "tools", "evaluator": "evaluator"})
        graph_builder.add_edge("tools", "worker")
        graph_builder.add_conditional_edges("evaluator", self.evaluator_router, {"worker": "worker", "END": END})
        # no end edge, embeded in conditional edge already
        self.graph = graph_builder.compile(checkpointer=self.memory)

    async def run_superstep(self, message, success_criteria, history):
        config = {"configurable": {"thread_id": self.sidekick_id}}
        state = {"messages": message,
                 "success_criteria": success_criteria or "The answer should be clear and accurate",
                 "feedback_on_work": None,
                 "success_criteria_met": False,
                 "user_input_needed": False,
                }
        result = await self.graph.ainvoke(state, config=config)
        user = {"role": "user", "content": message} # a user message input to LLM
        reply = {"role": "assistant", "content": result["messages"][-2].content}
        feedback = {"role": "assistant", "content": result["messages"][-1].content}
    
        return history + [user, reply, feedback]

    def cleanup(self):
        if self.browser: 
            try: 
                loop = asyncio.get_running_loop()
                loop.create_task(self.browswer.close())
                if self.playwright:
                    loop.create_task(self.playwright.stop())
            except RuntimeError:
                asyncio.run(self.browswer.close())
                if self.playwright:
                    asyncio.run(self.playwright.stop())
        