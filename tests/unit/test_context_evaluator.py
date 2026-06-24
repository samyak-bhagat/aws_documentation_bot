"""Unit tests for agents/nodes/context_evaluator.py — no LLM or MCP required."""

from agents.nodes.context_evaluator import context_evaluator_node, _MIN_CONTEXT_CHARS


class TestContextEvaluator:
    def test_sufficient_context(self):
        state = {"user_query": "test", "context": "x" * _MIN_CONTEXT_CHARS}
        result = context_evaluator_node(state)
        assert result["context_sufficient"] is True

    def test_insufficient_context(self):
        state = {"user_query": "test", "context": "x" * (_MIN_CONTEXT_CHARS - 1)}
        result = context_evaluator_node(state)
        assert result["context_sufficient"] is False

    def test_empty_context_insufficient(self):
        state = {"user_query": "test", "context": ""}
        result = context_evaluator_node(state)
        assert result["context_sufficient"] is False

    def test_missing_context_insufficient(self):
        state = {"user_query": "test"}
        result = context_evaluator_node(state)
        assert result["context_sufficient"] is False
