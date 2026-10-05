import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import HumanMessage
from langchain_aws import ChatBedrockConverse
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from dotenv import load_dotenv
import os

from evals.golden_dataset import GOLDEN_DATASET
from evals.graders import (
    grade_tools_called,
    grade_structured_output,
    grade_match_score_range,
    grade_gaps_count,
    grade_no_error,
    grade_llm_judge,
    expects_structured_output,
)

load_dotenv()

BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
PASS_THRESHOLD = 0.80


class GapAnalysis(BaseModel):
    match_score: int
    top_gaps: list[str]
    pitch: str
    recommend_roles: list[str]


async def run_single_eval(example: dict, index: int, resume_text: str) -> dict:
    """Run one eval case - fresh agent per case to avoid memory contamination."""
    
    
    
    mcp_client = MultiServerMCPClient({
        "notes": {
            "command": sys.executable,
            "args": ["servers/notes_server.py"],
            "transport": "stdio",
        },
        "search": {
            "url": "http://127.0.0.1:8000/mcp",
            "transport": "streamable_http",
        },
    })

    try:
        tools = await mcp_client.get_tools()
        llm = ChatBedrockConverse(model=BEDROCK_MODEL_ID, region_name=BEDROCK_REGION)
        agent = create_agent(
            model=llm,
            tools=tools,
            checkpointer=InMemorySaver(),
            system_prompt=(
                "You are a professional career coach.\n\n"
                f"Resume:\n{resume_text}\n\n"
                "When the user shares a job URL, scrape it, compare it against the resume, "
                "and save the analysis with save_research before you reply."
            ),
        )

        config = {"configurable": {"thread_id": f"eval-{index}"}}
        run_result = await agent.ainvoke(
            {"messages": [HumanMessage(content=example["input"])]},
            config=config,
        )

        # only run structured output for cases that expect it
        parsed = None
        needs_structured = expects_structured_output(example)
        if needs_structured:
            structured_llm = llm.with_structured_output(GapAnalysis)
            agent_text = str(run_result["messages"][-1].content)
            try:
                parsed = structured_llm.invoke(
                    f"Extract a structured gap analysis from this:\n\n{agent_text}"
                )
            except Exception as e:
                parsed = None

        example["resume_text"] = resume_text  # ← must be inside try

        scores = {
        "no_error":         grade_no_error(run_result, example),
        "tools_called":     grade_tools_called(run_result, example),
        "structured_valid": grade_structured_output(run_result, example, parsed),
        "score_range":      grade_match_score_range(run_result, example, parsed),
        "gaps_count":       grade_gaps_count(run_result, example, parsed),
        "llm_judge":        grade_llm_judge(run_result, example, parsed, llm),
    }

        overall = sum(s["score"] for s in scores.values()) / len(scores)
        return {
            "input": example["input"][:60] + "...",
            "difficulty": example.get("difficulty", "unknown"),
            "scores": scores,
            "overall": overall,
            "passed": overall >= PASS_THRESHOLD,
        }

    except Exception as e:
        return {
            "input": example["input"][:60] + "...",
            "difficulty": example.get("difficulty", "unknown"),
            "scores": {"run_error": {"score": 0.0, "reason": str(e)}},
            "overall": 0.0,
            "passed": False,
        }


async def run_eval_suite():
    resume_text = (PROJECT_ROOT / "evals/fixtures/test_resume.txt").read_text(encoding="utf-8")
    results = []

    print(f"Running {len(GOLDEN_DATASET)} evals...\n")
    print("NOTE: Make sure search server is running on port 8000 first.\n")

    for index, example in enumerate(GOLDEN_DATASET, start=1):
        print(f"[{index}/{len(GOLDEN_DATASET)}] {example['input'][:60]}...")
        result = await run_single_eval(example, index, resume_text)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        print(f"  {status} overall={result['overall']:.2f} difficulty={result['difficulty']}")
        for name, score in result["scores"].items():
            marker = "OK" if score["score"] >= PASS_THRESHOLD else "NO"
            print(f"    {marker} {name}: {score['score']:.2f} - {score['reason']}")
        print()

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print("=" * 60)
    print(f"RESULTS: {passed}/{total} passed ({passed/total:.1%})")
    print(f"Threshold: {PASS_THRESHOLD:.0%}")

    return results


if __name__ == "__main__":
    asyncio.run(run_eval_suite())