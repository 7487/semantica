"""
Rete Algorithm Engine Module

This module provides Rete algorithm implementation for efficient rule-based
reasoning, using a network of alpha and beta nodes for pattern matching.

Key Features:
    - Rete algorithm implementation for efficient rule matching
    - Alpha node pattern matching
    - Beta node join operations
    - Terminal node activation
    - Incremental fact processing
    - Performance optimization for large rule sets

Main Classes:
    - ReteEngine: Rete algorithm implementation
    - ReteNode: Base Rete network node
    - AlphaNode: Alpha node for single condition matching
    - BetaNode: Beta node for join operations
    - TerminalNode: Terminal node for rule activation
    - Fact: Dataclass for fact representation
    - Match: Dataclass for pattern matches

Example Usage:
    >>> from semantica.reasoning import ReteEngine, Fact
    >>> engine = ReteEngine()
    >>> engine.add_rule(rule)
    >>> fact = Fact("f1", "Person", ["John"])
    >>> engine.add_fact(fact)
    >>> matches = engine.get_matches()

Author: Semantica Contributors
License: MIT
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .reasoner import Fact, Rule

logger = get_logger("rete_engine")


def unify_condition(
    condition: Any,
    fact: Fact,
    initial_bindings: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, str]]:
    """Unify a condition pattern against a fact.

    A condition is a pattern string such as ``"Person(?x)"`` or
    ``"knows(?x, ?y)"`` where tokens beginning with ``?`` are variables.
    The fact is rendered via its ``__str__`` representation
    (``predicate(arg1, arg2)``) and matched against the pattern.

    This mirrors ``Reasoner._match_pattern`` but is self-contained so the
    RETE engine does not need a live ``Reasoner`` instance.

    Args:
        condition: The condition pattern (string). Non-string conditions
            are stringified before matching.
        fact: The fact to test.
        initial_bindings: Bindings already established upstream. Variables
            already bound must match the corresponding literal in the fact.

    Returns:
        A dict of variable bindings if the fact unifies with the condition,
        otherwise ``None``.
    """
    bindings = dict(initial_bindings or {})
    pattern = condition if isinstance(condition, str) else str(condition)
    fact_str = str(fact)

    # Split on ?var placeholders, escaping only the literal segments so that
    # the surrounding parentheses/commas are matched literally.
    segments = re.split(r"(\?\w+)", pattern)
    seen_vars: Set[str] = set()
    p_regex = ""
    for seg in segments:
        if seg.startswith("?"):
            var_name = seg[1:]
            if var_name in bindings:
                # Already bound — require the exact literal value.
                p_regex += re.escape(bindings[var_name])
            elif var_name in seen_vars:
                # Same variable used twice — enforce a backreference.
                p_regex += f"(?P={var_name})"
            else:
                p_regex += f"(?P<{var_name}>.+?)"
                seen_vars.add(var_name)
        else:
            p_regex += re.escape(seg)
    p_regex = f"^{p_regex}$"

    try:
        match = re.match(p_regex, fact_str)
    except re.error as e:
        logger.warning(
            "unify_condition failed to compile/match condition "
            "%r (regex: %r) against fact %r: %s",
            pattern,
            p_regex,
            fact_str,
            e,
        )
        return None
    except Exception as e:  # noqa: BLE001 - mirror Reasoner._match_pattern
        logger.warning(
            "unify_condition unexpected error matching condition "
            "%r (regex: %r) against fact %r: %s",
            pattern,
            p_regex,
            fact_str,
            e,
        )
        return None
    if not match:
        return None

    for var, value in match.groupdict().items():
        if var in bindings and bindings[var] != value:
            return None  # Binding conflict.
        bindings[var] = value
    return bindings


@dataclass
class Token:
    """A partial match flowing through the Rete network.

    A token represents an ordered collection of concrete facts that have
    been unified so far, together with the consistent variable bindings
    accumulated across those facts.

    Alpha nodes emit single-fact tokens. Beta nodes merge a left token and
    a right token into a new token whose ``facts`` are the concatenation of
    both sides (preserving condition order) and whose ``bindings`` are the
    consistent union of both sides.
    """

    facts: List[Fact] = field(default_factory=list)
    bindings: Dict[str, str] = field(default_factory=dict)


@dataclass
class Match:
    """Pattern match."""

    rule: Rule
    facts: List[Fact]
    bindings: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


class ReteNode:
    """Base Rete network node."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.children: List[ReteNode] = []


class AlphaNode(ReteNode):
    """Alpha node for single condition matching."""

    def __init__(self, node_id: str, condition: Any):
        super().__init__(node_id)
        self.condition = condition
        # Single-fact tokens produced by unifying each matched fact with
        # this node's condition.
        self.tokens: List[Token] = []

    def add_fact(self, fact: Fact) -> Optional[Token]:
        """Add fact if it matches the condition, returning its token.

        Returns the single-fact ``Token`` produced by unification when the
        fact matches, otherwise ``None``.
        """
        bindings = self._matches(fact)
        if bindings is not None:
            token = Token(facts=[fact], bindings=dict(bindings))
            self.tokens.append(token)
            return token
        return None

    def _matches(self, fact: Fact) -> Optional[Dict[str, str]]:
        """Check if fact matches the alpha node condition.

        Returns the variable bindings produced by unification if the fact
        matches, otherwise ``None``. An empty dict signals a match with no
        variables (still distinct from ``None``).
        """
        return unify_condition(self.condition, fact)


class BetaNode(ReteNode):
    """Beta node for joining conditions."""

    def __init__(self, node_id: str, left: ReteNode, right: ReteNode):
        super().__init__(node_id)
        self.left = left
        self.right = right
        # Token memories for each side. Incoming tokens are stored here so
        # that later-arriving tokens on the opposite side can be joined
        # against every token already seen (chained joins).
        self.left_tokens: List[Token] = []
        self.right_tokens: List[Token] = []

    def join(self, left_token: Token, right_token: Token) -> Optional[Token]:
        """Join a left token with a right token.

        Returns a new merged ``Token`` (facts concatenated in condition
        order, bindings unified) when the two tokens are consistent,
        otherwise ``None`` on a binding conflict.
        """
        merged = dict(left_token.bindings)
        for var, value in right_token.bindings.items():
            if var in merged and merged[var] != value:
                return None  # Binding conflict — cannot join.
            merged[var] = value
        return Token(
            facts=list(left_token.facts) + list(right_token.facts),
            bindings=merged,
        )


class TerminalNode(ReteNode):
    """Terminal node representing rule activation."""

    def __init__(self, node_id: str, rule: Rule):
        super().__init__(node_id)
        self.rule = rule
        self.activations: List[Match] = []

    def activate(self, match: Match) -> None:
        """Activate rule."""
        self.activations.append(match)


class ReteEngine:
    """
    Rete algorithm implementation for efficient rule matching.

    • Rete algorithm implementation
    • Rule network construction and optimization
    • Pattern matching and conflict resolution
    • Performance optimization
    • Error handling and recovery
    • Advanced Rete features
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize Rete engine.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("rete_engine")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.network: Dict[str, ReteNode] = {}
        self.facts: List[Fact] = []
        self.fact_counter = 0
        self.node_counter = 0

    def build_network(self, rules: List[Rule]) -> None:
        """
        Build Rete network from rules.

        Args:
            rules: List of rules
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="ReteEngine",
            message=f"Building Rete network from {len(rules)} rules",
        )

        try:
            self.network.clear()

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Adding {len(rules)} rules to network..."
            )
            for rule in rules:
                self._add_rule_to_network(rule)

            self.logger.info(
                f"Built Rete network with {len(self.network)} nodes "
                f"for {len(rules)} rules"
            )
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=(
                    f"Built Rete network with {len(self.network)} nodes "
                    f"for {len(rules)} rules"
                ),
            )

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _add_rule_to_network(self, rule: Rule) -> None:
        """Add rule to Rete network."""
        # Create alpha nodes for each condition
        alpha_nodes = []
        for condition in rule.conditions:
            node_id = f"alpha_{self.node_counter}"
            self.node_counter += 1
            alpha_node = AlphaNode(node_id, condition)
            alpha_nodes.append(alpha_node)
            self.network[node_id] = alpha_node

        # Create beta nodes for joining
        if len(alpha_nodes) > 1:
            current = alpha_nodes[0]
            for i in range(1, len(alpha_nodes)):
                node_id = f"beta_{self.node_counter}"
                self.node_counter += 1
                beta_node = BetaNode(node_id, current, alpha_nodes[i])
                self.network[node_id] = beta_node
                # Wire the beta node as a child of both its inputs so facts
                # propagating from either side reach the join.
                current.children.append(beta_node)
                alpha_nodes[i].children.append(beta_node)
                current = beta_node
            final_node = current
        else:
            final_node = alpha_nodes[0] if alpha_nodes else None

        # Create terminal node
        if final_node:
            node_id = f"terminal_{self.node_counter}"
            self.node_counter += 1
            terminal_node = TerminalNode(node_id, rule)
            final_node.children.append(terminal_node)
            self.network[node_id] = terminal_node

    def add_fact(self, fact: Fact) -> None:
        """
        Add fact to working memory.

        Args:
            fact: Fact to add
        """
        self.facts.append(fact)

        # Propagate through network
        self._propagate_fact(fact)

    def _propagate_fact(self, fact: Fact) -> None:
        """Propagate fact through Rete network."""
        # Find matching alpha nodes
        for node_id, node in self.network.items():
            if isinstance(node, AlphaNode):
                token = node.add_fact(fact)
                if token is not None:
                    # Propagate the single-fact token to children.
                    self._propagate_token(node, token)

    def _propagate_token(self, source: ReteNode, token: Token) -> None:
        """Propagate ``token`` (arriving from ``source``) to its children.

        A ``Token`` carries the ordered facts and consistent bindings of a
        partial match. Beta children attempt joins and, on success, emit a
        new merged token downstream; terminal children turn the token into a
        rule activation using the token's complete facts and bindings.
        """
        for child in source.children:
            if isinstance(child, BetaNode):
                self._propagate_to_beta(child, source, token)
            elif isinstance(child, TerminalNode):
                match = Match(
                    rule=child.rule,
                    facts=list(token.facts),
                    bindings=dict(token.bindings),
                    confidence=1.0,
                )
                child.activate(match)

    def _propagate_to_beta(
        self,
        beta: "BetaNode",
        source: ReteNode,
        token: Token,
    ) -> None:
        """Attempt joins at ``beta`` for a token arriving from one side.

        The incoming token is stored in the corresponding side's memory,
        then joined against every token already recorded on the opposite
        side. Each successful join produces a new merged token that is
        propagated further downstream, enabling correct chained joins across
        three or more conditions.
        """
        if source is beta.left:
            beta.left_tokens.append(token)
            for right_token in list(beta.right_tokens):
                merged = beta.join(token, right_token)
                if merged is not None:
                    self._propagate_token(beta, merged)
        elif source is beta.right:
            beta.right_tokens.append(token)
            for left_token in list(beta.left_tokens):
                merged = beta.join(left_token, token)
                if merged is not None:
                    self._propagate_token(beta, merged)

    def match_patterns(self, facts: Optional[List[Fact]] = None) -> List[Match]:
        """
        Match patterns using Rete algorithm.

        Args:
            facts: Optional facts to match (uses working memory if not provided)

        Returns:
            List of matches
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="ReteEngine",
            message="Matching patterns using Rete algorithm",
        )

        try:
            if facts:
                # Add facts to working memory
                self.progress_tracker.update_tracking(
                    tracking_id,
                    message=f"Adding {len(facts)} facts to working memory...",
                )
                for fact in facts:
                    self.add_fact(fact)

            # Collect all activations
            self.progress_tracker.update_tracking(
                tracking_id, message="Collecting pattern matches..."
            )
            matches = []
            for node_id, node in self.network.items():
                if isinstance(node, TerminalNode):
                    matches.extend(node.activations)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Found {len(matches)} pattern matches",
            )
            return matches

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def execute_matches(self, matches: Optional[List[Match]] = None) -> List[Any]:
        """
        Execute matched rules.

        Args:
            matches: Optional matches to execute (uses current matches if not provided)

        Returns:
            List of inference results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="reasoning",
            submodule="ReteEngine",
            message="Executing matched rules",
        )

        try:
            if matches is None:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Matching patterns..."
                )
                matches = self.match_patterns()

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Executing {len(matches)} matched rules..."
            )
            results = []
            for match in matches:
                try:
                    # Execute rule
                    result = match.rule.conclusion
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Error executing match: {e}")

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Executed {len(matches)} matches: {len(results)} results",
            )
            return results

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def reset(self) -> None:
        """Reset Rete engine."""
        self.facts.clear()
        for node in self.network.values():
            if isinstance(node, AlphaNode):
                node.tokens.clear()
            elif isinstance(node, BetaNode):
                node.left_tokens.clear()
                node.right_tokens.clear()
            elif isinstance(node, TerminalNode):
                node.activations.clear()

    def get_network_stats(self) -> Dict[str, Any]:
        """Get network statistics."""
        alpha_count = sum(1 for n in self.network.values() if isinstance(n, AlphaNode))
        beta_count = sum(1 for n in self.network.values() if isinstance(n, BetaNode))
        terminal_count = sum(
            1 for n in self.network.values() if isinstance(n, TerminalNode)
        )

        return {
            "total_nodes": len(self.network),
            "alpha_nodes": alpha_count,
            "beta_nodes": beta_count,
            "terminal_nodes": terminal_count,
            "facts": len(self.facts),
        }
