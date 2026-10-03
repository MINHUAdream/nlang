"""Standalone parser for the first n RTM source subset.

The parser deliberately produces n-owned dataclasses rather than the legacy tl
AST.  Later lowering stages can therefore evolve without preserving tl's
statement grammar.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from n_ops import SCALAR_OPERATIONS


class NParseError(ValueError):
    """A source error with a byte/character offset."""


@dataclass(frozen=True)
class NFieldDecl:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    device: str


@dataclass(frozen=True)
class NWaveOp:
    kind: str
    value: str | float | None = None


@dataclass(frozen=True)
class NEchoDecl:
    mode: str


@dataclass(frozen=True)
class NWaveDecl:
    name: str
    parameter: str
    result: str
    operations: tuple[NWaveOp, ...]
    echo: NEchoDecl
    fallback: str


@dataclass(frozen=True)
class NCommitDecl:
    wave: str
    field: str


@dataclass(frozen=True)
class NGoalTarget:
    direction: str
    metric: str


@dataclass(frozen=True)
class NGoalOption:
    name: str
    metrics: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class NGoalDecl:
    name: str
    targets: tuple[NGoalTarget, ...]
    required_features: tuple[str, ...]
    options: tuple[NGoalOption, ...]


@dataclass(frozen=True)
class NSynthesizeDecl:
    goal: str
    max_rounds: int | None = None


@dataclass(frozen=True)
class NModule:
    name: str | None
    fields: tuple[NFieldDecl, ...]
    waves: tuple[NWaveDecl, ...]
    commits: tuple[NCommitDecl, ...]
    goals: tuple[NGoalDecl, ...] = ()
    syntheses: tuple[NSynthesizeDecl, ...] = ()


@dataclass(frozen=True)
class _Token:
    kind: str
    text: str
    pos: int


_TOKEN_RE = re.compile(
    r"(?P<space>\s+)|(?P<comment>//[^\n]*)|(?P<arrow>->)|"
    r"(?P<number>(?:\d+(?:\.\d*)?|\.\d+))|"
    r"(?P<ident>[A-Za-z_][A-Za-z0-9_]*)|(?P<punct>[:;{}\[\](),])"
)


def _lex(source: str) -> tuple[_Token, ...]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(source):
        match = _TOKEN_RE.match(source, pos)
        if match is None:
            raise NParseError(f"unrecognized character at offset {pos}: {source[pos]!r}")
        kind = match.lastgroup
        text = match.group(0)
        pos = match.end()
        if kind in {"space", "comment"}:
            continue
        tokens.append(_Token(kind, text, match.start()))
    tokens.append(_Token("eof", "", len(source)))
    return tuple(tokens)


class _Parser:
    def __init__(self, source: str):
        self.tokens = _lex(source)
        self.index = 0

    @property
    def current(self) -> _Token:
        return self.tokens[self.index]

    def take(self, text: str | None = None, kind: str | None = None) -> _Token:
        token = self.current
        if text is not None and token.text != text:
            raise NParseError(f"expected {text!r} at offset {token.pos}, got {token.text!r}")
        if kind is not None and token.kind != kind:
            raise NParseError(f"expected {kind} at offset {token.pos}, got {token.kind}")
        self.index += 1
        return token

    def maybe(self, text: str) -> bool:
        if self.current.text == text:
            self.index += 1
            return True
        return False

    def ident(self) -> str:
        return self.take(kind="ident").text

    def parse(self) -> NModule:
        module_name: str | None = None
        fields: list[NFieldDecl] = []
        waves: list[NWaveDecl] = []
        commits: list[NCommitDecl] = []
        goals: list[NGoalDecl] = []
        syntheses: list[NSynthesizeDecl] = []
        field_names: set[str] = set()
        wave_names: set[str] = set()
        goal_names: set[str] = set()
        while self.current.kind != "eof":
            if self.maybe("module"):
                if module_name is not None:
                    raise NParseError("duplicate module declaration")
                module_name = self.ident()
                self.take(";")
            elif self.maybe("field"):
                field = self.parse_field()
                if field.name in field_names:
                    raise NParseError(f"duplicate field {field.name!r}")
                field_names.add(field.name)
                fields.append(field)
            elif self.maybe("wave"):
                wave = self.parse_wave()
                if wave.name in wave_names:
                    raise NParseError(f"duplicate wave {wave.name!r}")
                wave_names.add(wave.name)
                waves.append(wave)
            elif self.maybe("commit"):
                commits.append(self.parse_commit())
            elif self.maybe("goal"):
                goal = self.parse_goal()
                if goal.name in goal_names:
                    raise NParseError(f"duplicate goal {goal.name!r}")
                goal_names.add(goal.name)
                goals.append(goal)
            elif self.maybe("synthesize"):
                syntheses.append(self.parse_synthesize())
            else:
                token = self.current
                raise NParseError(f"unexpected token {token.text!r} at offset {token.pos}")
        for commit in commits:
            if commit.wave not in wave_names:
                raise NParseError(f"commit references unknown wave {commit.wave!r}")
            if commit.field not in field_names:
                raise NParseError(f"commit references unknown field {commit.field!r}")
        for synthesis in syntheses:
            if synthesis.goal not in goal_names:
                raise NParseError(f"synthesize references unknown goal {synthesis.goal!r}")
        return NModule(
            module_name,
            tuple(fields),
            tuple(waves),
            tuple(commits),
            tuple(goals),
            tuple(syntheses),
        )

    def parse_field(self) -> NFieldDecl:
        name = self.ident()
        self.take(":")
        dtype = self.ident()
        if dtype not in {"f32", "f64"}:
            raise NParseError(f"unsupported field type {dtype!r}")
        self.take("[")
        shape: list[int] = []
        while True:
            number = self.take(kind="number").text
            if "." in number:
                raise NParseError(f"field dimensions must be integers at offset {self.current.pos}")
            shape.append(int(number))
            if not self.maybe(","):
                break
        self.take("]")
        self.take("layout")
        layout = self.ident()
        self.take("device")
        device = self.ident()
        self.take(";")
        if not shape or any(d <= 0 for d in shape):
            raise NParseError(f"field {name!r} must have positive dimensions")
        return NFieldDecl(name, dtype, tuple(shape), layout, device)

    def parse_wave(self) -> NWaveDecl:
        name = self.ident()
        self.take("(")
        parameter = self.ident()
        self.take(")")
        self.take("->")
        result = self.ident()
        self.take("{")
        operations: list[NWaveOp] = []
        echo: NEchoDecl | None = None
        fallback: str | None = None
        while not self.maybe("}"):
            if self.maybe("read"):
                operations.append(NWaveOp("read", self.ident()))
                self.take(";")
            elif self.maybe("write"):
                operations.append(NWaveOp("write", self.ident()))
                self.take(";")
            elif self.maybe("delta"):
                operation = self.ident()
                if operation not in SCALAR_OPERATIONS:
                    raise NParseError(f"unknown wave delta operation {operation!r}")
                value = float(self.take(kind="number").text)
                operations.append(NWaveOp("delta", operation))
                operations.append(NWaveOp("delta_value", value))
                self.take(";")
            elif self.maybe("echo"):
                mode = self.ident()
                if mode != "exact":
                    raise NParseError(f"unknown echo mode {mode!r}")
                if echo is not None:
                    raise NParseError("duplicate echo declaration")
                echo = NEchoDecl(mode)
                self.take(";")
            elif self.maybe("fallback"):
                fallback = self.ident()
                if fallback != "reject":
                    raise NParseError(f"unknown fallback policy {fallback!r}")
                self.take(";")
            else:
                token = self.current
                raise NParseError(f"unexpected wave token {token.text!r} at offset {token.pos}")
        if echo is None:
            raise NParseError(f"wave {name!r} requires an echo")
        if fallback is None:
            raise NParseError(f"wave {name!r} requires a fallback")
        kinds = [item.kind for item in operations]
        if kinds != ["read", "write", "delta", "delta_value"]:
            raise NParseError(
                "RTM wave must contain read, write, and a supported scalar delta in order"
            )
        if operations[0].value != parameter or operations[1].value != parameter:
            raise NParseError(f"wave {name!r} must read and write its parameter")
        return NWaveDecl(name, parameter, result, tuple(operations), echo, fallback)

    def parse_commit(self) -> NCommitDecl:
        wave = self.ident()
        self.take("into")
        field = self.ident()
        self.take(";")
        return NCommitDecl(wave, field)

    def parse_goal(self) -> NGoalDecl:
        name = self.ident()
        self.take("{")
        targets: list[NGoalTarget] = []
        required: list[str] = []
        options: list[NGoalOption] = []
        option_names: set[str] = set()
        while not self.maybe("}"):
            if self.maybe("target") or self.maybe("objective"):
                direction = self.ident()
                if direction not in {"minimize", "maximize"}:
                    raise NParseError(f"unknown goal direction {direction!r}")
                metric = self.ident()
                self.take(";")
                targets.append(NGoalTarget(direction, metric))
            elif self.maybe("require"):
                self.take("[")
                while True:
                    required.append(self.ident())
                    if not self.maybe(","):
                        break
                self.take("]")
                self.take(";")
            elif self.maybe("option"):
                option = self.parse_option()
                if option.name in option_names:
                    raise NParseError(f"duplicate goal option {option.name!r}")
                option_names.add(option.name)
                options.append(option)
            else:
                token = self.current
                raise NParseError(f"unexpected goal token {token.text!r} at offset {token.pos}")
        if not targets:
            raise NParseError(f"goal {name!r} requires a target")
        if not options:
            raise NParseError(f"goal {name!r} requires an option")
        return NGoalDecl(name, tuple(targets), tuple(dict.fromkeys(required)), tuple(options))

    def parse_option(self) -> NGoalOption:
        name = self.ident()
        self.take("{")
        metrics: list[tuple[str, float]] = []
        metric_names: set[str] = set()
        while not self.maybe("}"):
            metric = self.ident()
            if metric in metric_names:
                raise NParseError(f"duplicate metric {metric!r} in option {name!r}")
            metric_names.add(metric)
            self.take(":")
            value = float(self.take(kind="number").text)
            self.take(";")
            metrics.append((metric, value))
        self.maybe(";")
        if not metrics:
            raise NParseError(f"option {name!r} requires a metric")
        return NGoalOption(name, tuple(metrics))

    def parse_synthesize(self) -> NSynthesizeDecl:
        goal = self.ident()
        max_rounds: int | None = None
        if self.maybe("max_rounds"):
            token = self.take(kind="number")
            if "." in token.text or int(float(token.text)) < 1:
                raise NParseError("max_rounds must be a positive integer")
            max_rounds = int(token.text)
        self.take(";")
        return NSynthesizeDecl(goal, max_rounds)


def parse(source: str) -> NModule:
    """Parse n RTM source without invoking the legacy tl parser."""

    return _Parser(source).parse()


__all__ = [
    "NCommitDecl",
    "NEchoDecl",
    "NFieldDecl",
    "NGoalDecl",
    "NGoalOption",
    "NGoalTarget",
    "NModule",
    "NParseError",
    "NSynthesizeDecl",
    "NWaveDecl",
    "NWaveOp",
    "parse",
]
