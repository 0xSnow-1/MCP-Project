import json


def expects_structured_output(expected: dict) -> bool:
    """Whether this case is supposed to yield a parsed gap analysis."""
    return (
        expected.get("expected_match_score_above") is not None
        or expected.get("expected_match_score_below") is not None
        or expected.get("expected_gaps_min") is not None
    )


def _get_tool_calls(run_result: dict) -> list[str]:
    """Extract all tool names called during the agent run."""
    tools_called = []
    for message in run_result["messages"]:
        for tool_call in getattr(message, "tool_calls", []) or []:
            name = tool_call.get("name")
            if name:
                tools_called.append(name)
    return tools_called


def _final_text(run_result: dict) -> str:
    """Get the last message content as a string."""
    return str(run_result["messages"][-1].content)


def grade_tools_called(run_result: dict, expected: dict) -> dict:
    """Check that all expected tools were actually called."""
    expected_tools = expected.get("expected_tools_called", [])
    if not expected_tools:
        return {"score": 1.0, "reason": "No tools expected - skipped"}

    called = _get_tool_calls(run_result)
    found = [t for t in expected_tools if t in called]
    missing = [t for t in expected_tools if t not in called]
    score = len(found) / len(expected_tools)

    return {
        "score": score,
        "reason": f"Found: {found} | Missing: {missing}",
    }


def grade_structured_output(run_result: dict, expected: dict, parsed) -> dict:
    """Check that the structured output has valid populated fields."""
    if parsed is None:
        if expects_structured_output(expected):
            return {"score": 0.0, "reason": "Structured output expected but parsing failed"}
        # cases where we don't run structured output
        return {"score": 1.0, "reason": "No structured output expected"}

    issues = []
    if not isinstance(parsed.match_score, int):
        issues.append("match_score is not an int")
    if not (0 <= parsed.match_score <= 100):
        issues.append(f"match_score {parsed.match_score} out of 0-100 range")
    if not parsed.top_gaps:
        issues.append("top_gaps is empty")
    if not parsed.pitch:
        issues.append("pitch is empty")
    if not parsed.recommend_roles:
        issues.append("recommend_roles is empty")

    return {
        "score": 0.0 if issues else 1.0,
        "reason": f"Issues: {issues}" if issues else "All fields valid",
    }


def grade_match_score_range(run_result: dict, expected: dict, parsed) -> dict:
    """Check the match score is in the expected range."""
    above = expected.get("expected_match_score_above")
    below = expected.get("expected_match_score_below")

    if above is None and below is None:
        return {"score": 1.0, "reason": "No score range expected"}
    if parsed is None:
        return {"score": 0.0, "reason": "Score range expected but no structured output to read"}

    score = parsed.match_score
    if above and score < above:
        return {"score": 0.0, "reason": f"Score {score} below expected minimum {above}"}
    if below and score > below:
        return {"score": 0.0, "reason": f"Score {score} above expected maximum {below}"}

    return {"score": 1.0, "reason": f"Score {score} within expected range"}


def grade_gaps_count(run_result: dict, expected: dict, parsed) -> dict:
    """Check that enough gaps were identified."""
    min_gaps = expected.get("expected_gaps_min")
    if min_gaps is None:
        return {"score": 1.0, "reason": "No gap count expected"}
    if parsed is None:
        return {"score": 0.0, "reason": "Gap count expected but no structured output to read"}

    count = len(parsed.top_gaps)
    passed = count >= min_gaps
    return {
        "score": 1.0 if passed else 0.0,
        "reason": f"Found {count} gaps, expected at least {min_gaps}",
    }


def grade_no_error(run_result: dict, expected: dict) -> dict:
    """Check the agent didn't crash or return error text."""
    text = _final_text(run_result).lower()
    signals = ["traceback", "exception:", "tool failed", "internal server error"]
    found = [s for s in signals if s in text]
    return {
        "score": 0.0 if found else 1.0,
        "reason": f"Error signals found: {found}" if found else "No errors detected",
    }


def grade_llm_judge(run_result: dict, expected: dict, parsed, llm) -> dict:
    """LLM-as-judge scores the quality of the gap analysis."""
    if parsed is None:
        if expects_structured_output(expected):
            return {"score": 0.0, "reason": "Gap analysis expected but none was parsed to judge"}
        return {"score": 1.0, "reason": "No structured output to judge"}
    resume = expected.get("resume_text", "not provided")

    prompt = f"""You are evaluating the quality of a job gap analysis produced by a career coach AI.
    
    
IMPORTANT: The agent had access to this candidate resume:
{resume}

User input: {expected["input"]}

Gap analysis produced:
- Match score: {parsed.match_score}/100
- Gaps identified: {parsed.top_gaps}
- Pitch: {parsed.pitch}
- Recommended roles: {parsed.recommend_roles}

Score from 0.0 to 1.0 based on:
- Is the match score reasonable given the input? (0.0-0.3)
- Are the gaps specific and actionable? (0.0-0.3)
- Is the pitch concise and honest? (0.0-0.2)
- Are recommended roles relevant? (0.0-0.2)

Return ONLY valid JSON with no markdown:
{{"score": <float 0.0-1.0>, "reason": "<one sentence>"}}"""

    try:
        response = llm.invoke(prompt)
        text = str(response.content).strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        result = json.loads(text[start:end])
        return {
            "score": max(0.0, min(1.0, float(result["score"]))),
            "reason": str(result["reason"]),
        }
    except Exception as e:
        return {"score": 0.0, "reason": f"Judge failed: {e}"}