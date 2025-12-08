from typing import List
from pydantic import BaseModel

from agents import Agent, Runner

NUMBER_OF_SEARCH = 3

search_plan_instruction = f"""You are deep research assistant.
Given a query, come up with a set of web searches to best answer the query. 
Output {NUMBER_OF_SEARCH} terms to query for."""


class WebSearchItem(BaseModel):
    reason: str
    "your reasoning for why this search is important to the query"

    query: str
    "the search term to use for the web search"


class WebSearchPlan(BaseModel):
    searches: List[WebSearchItem]
    """A list of web searches to perform to best answer the query"""


class PlannerAgent:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.agent = Agent(
            name="PlannerAgent",
            instructions=search_plan_instruction,
            model=model,
            output_type=WebSearchPlan,
        )

    async def plan_searches(self, query: str) -> WebSearchPlan:
        """Use planner_agent to plot out search terms."""
        result = await Runner.run(self.agent, f"Query: {query}")
        return result.final_output
    

import json
import asyncio
from typing import List

from agents import Agent, Runner, function_tool
from agents.model_settings import ModelSettings

from trd_agent.tools.search_perplexity import PerplexitySearchTool



search_instruction = """You are a research assistant. Given a search term, search the web for that term, 
and produce a concise summary of the results. 
The summary will be sonsumed by someone synthesizing a full report, so it is vital that: 
+ The summary must be 2-3 paragraphs and less than 300 words, writen succintly, no complete sentence or good grammar. 
+ The summary captures the main points, ignore any fluff, no additional commentary."""


class SearchAgent:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._search_tool_perplexity = PerplexitySearchTool()

        search_tool = self._search_tool_perplexity

        @function_tool
        def perplexity_search(query: str) -> str:
            """
            Perform Perplexity web search and return JSON results.

            Args:
                query: Natural-language search query.
            """
            result = search_tool.run(query=query)
            return json.dumps(result)

        self.agent = Agent(
            name="Search agent",
            instructions=search_instruction,
            tools=[perplexity_search],
            model=model,
            model_settings=ModelSettings(tool_choice="required"),
        )

    async def _search(self, item: WebSearchItem) -> str:
        """Use search agent to run a web search for each item in search plan."""
        input_text = (
            f"Search term: {item.query} \n "
            f"Search strategy reasoning: {item.reason}"
        )
        result = await Runner.run(self.agent, input_text)
        return result.final_output

    async def perform_searches(self, search_plan: WebSearchPlan) -> List[str]:
        """Call search() for each search item in search plan."""
        tasks = [asyncio.create_task(self._search(item)) for item in search_plan.searches]
        results = await asyncio.gather(*tasks)
        return list(results)

from typing import List

from pydantic import BaseModel

from agents import Agent, Runner


search_exec_instruction = """You are researcher taksed with writing cohesive report for a research query. 
You are given the original query and some initial research done by a research assistant.
Come up with an outline for the report describing the structure and flow of the report.
Then generate the report and return that as your final output.
The final output should be in markdown format, lengthly, and in detailed. Aim for 10 pages of content with at least 1000 words.
"""


class ReportData(BaseModel):
    short_summary: str
    """A short 2~3 sentence summary of the findings"""

    markdown_report: str
    """The final report"""

    follow_up_question: list[str]
    """Suggested topics to research further"""


class DeepResearch:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.agent = Agent(
            name="WriterAgent",
            instructions=search_exec_instruction,
            model=model,
            output_type=ReportData,
        )

    async def write_report(self, query: str, search_results: List[str]) -> ReportData:
        """Use writer agent to write a report based on the search results."""
        print("Thinking about the report..")
        input_text = (
            f"Original query: {query}\n summarized search results: {search_results}"
        )
        result = await Runner.run(self.agent, input_text)
        print("Finished writing report")
        return result.final_output


from typing import Dict

from agents import Agent, Runner, function_tool



subject_instruction = (
    "Given a message, you write a subject for a cold sales email that is likely to get a response"
)

html_instruction = (
    "Given a text email body which may have some markdown, convert it to an HTML email "
    "with simple, clear, compeling layout and design"
)

email_instruction = """You are email formatter and sender.
Given body of an email to be sent, you first use the subject_writer tool to write subject for the email.
Then, use the html_converter tool to convert to body to HTML.
Finally, use send_html_email tool to send out the email with subject and HTML body."""


class EmailAgent:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        subject_writer = Agent(
            name="Email subject writer",
            instructions=subject_instruction,
            model=model,
        )
        subject_tool = subject_writer.as_tool(
            tool_name="subject_writer",
            tool_description="Write a subject for a cold sales email",
        )

        html_converter = Agent(
            name="HTML email body converter",
            instructions=html_instruction,
            model=model,
        )
        html_tool = html_converter.as_tool(
            tool_name="html_converter",
            tool_description="Convert a text email body to an HTML email body",
        )

        @function_tool
        def send_html_email(subject: str, html_body: str) -> Dict[str, str]:
            """Send out an email with given subject and HTML body to all sales prospect."""
            print("pretending to send an html email")
            print("sending....")
            print(f"\n\n#############{subject}###########\n\n")
            print(f"\n\n#############{html_body}###########\n\n")
            print("done!")
            return {"status": "success"}

        self.agent = Agent(
            name="Email Manager",
            instructions=email_instruction,
            tools=[subject_tool, html_tool, send_html_email],
            model=model,
            handoff_description="Convert an email to HTML and send it",
        )

        # Optional: keep a convenience attribute matching old pattern if you used it
        self.tools = [subject_tool, html_tool, send_html_email]

    async def send_email(self, report: ReportData) -> ReportData:
        """Use email agent to send email."""
        print("writing email...")
        await Runner.run(self.agent, report.markdown_report)
        print("Email sent")
        return report

from agents import trace

class ResearchManager:
    """Minimal entry to run the whole research → report → email flow."""

    def __init__(self) -> None:
        self.planner = PlannerAgent()
        self.search_agent = SearchAgent()
        self.deep_research = DeepResearch()
        self.email_agent = EmailAgent()

    async def run(self, query: str) -> ReportData:
        """Full pipeline: plan searches, execute, write report, send email."""
        with trace("Research trace planned-write-email"):
            print("Starting search")

            search_plan: WebSearchPlan = await self.planner.plan_searches(query)
            search_result = await self.search_agent.perform_searches(search_plan)
            report = await self.deep_research.write_report(query, search_result)
            await self.email_agent.send_email(report)

            print("Done!")
            return report

    async def stream(self, query: str):
        """Async generator that yields progress + final report."""
        with trace("Research trace planned-write-email"):
            yield "Planning searches..."
            search_plan: WebSearchPlan = await self.planner.plan_searches(query)

            yield "Running web searches..."
            search_result = await self.search_agent.perform_searches(search_plan)

            yield "Writing report..."
            report = await self.deep_research.write_report(query, search_result)

            yield "Sending email..."
            await self.email_agent.send_email(report)

            yield "Done! Here is the report:\n\n" + report.markdown_report


