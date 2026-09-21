"""The judge: LongMemEval's own answer-checking protocol, not ours.

Templates are copied verbatim from the benchmark's evaluation script
(xiaowu0162/LongMemEval, src/evaluation/evaluate_qa.py): one template per
question type, a separate one for abstention questions (question ids carrying
``_abs``), the label is a yes/no from a model at temperature 0. The judge model
is deliberately a different model from the one that answered.

One deliberate addition. The benchmark reads "yes" anywhere in the reply, which
was fine for the model it was written against; a judge that reasons first emits
``<think>`` blocks, and with a small completion budget that reasoning is all
that comes back. Counting such a cell as a failed answer is not a measurement,
it is a silent zero. So the verdict is parsed explicitly: reasoning is removed,
a thought that never closed yields no verdict at all, and a cell without a
verdict is recorded as *unjudged* rather than folded into the score.
"""

from __future__ import annotations

import re

THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.I | re.S)
THINK_OPEN_RE = re.compile(r"<think\b", re.I)
THINK_CLOSE_RE = re.compile(r"</think\s*>", re.I)
THINK_ANY_TAG_RE = re.compile(r"</?think\b[^>]*>", re.I)
VERDICT_RE = re.compile(r"\b(yes|no)\b", re.I)

# A reasoning judge needs room for the thought and the verdict. The benchmark
# itself allows 16 completion tokens, which is why this is stated as a number
# that can be seen in a record rather than left to the caller's default.
JUDGE_MAX_TOKENS = 256


def strip_reasoning(raw: str) -> str:
    """The judge's visible answer: closed reasoning blocks removed."""
    return THINK_ANY_TAG_RE.sub(" ", THINK_BLOCK_RE.sub(" ", raw or "")).strip()


def parse_label(raw: str) -> str:
    """``yes``, ``no``, or ``""`` when the reply carries no verdict.

    A reasoning block that never closed means the reply was cut off inside the
    thought: no verdict was given, so nothing is claimed about the answer.
    """
    text = raw or ""
    if len(THINK_OPEN_RE.findall(text)) > len(THINK_CLOSE_RE.findall(text)):
        return ""
    visible = strip_reasoning(text)
    match = VERDICT_RE.search(visible)
    return match.group(1).lower() if match else ""

SIMPLE = ("I will give you a question, a correct answer, and a response from a model. "
          "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
          "If the response is equivalent to the correct answer or contains all the intermediate "
          "steps to get the correct answer, you should also answer yes. If the response only "
          "contains a subset of the information required by the answer, answer no. \n\n"
          "Question: {question}\n\nCorrect Answer: {answer}\n\nModel Response: {response}\n\n"
          "Is the model response correct? Answer yes or no only.")

TEMPORAL = ("I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
            "If the response is equivalent to the correct answer or contains all the intermediate "
            "steps to get the correct answer, you should also answer yes. If the response only "
            "contains a subset of the information required by the answer, answer no. In addition, "
            "do not penalize off-by-one errors for the number of days. If the question asks for the "
            "number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., "
            "predicting 19 days when the answer is 18), the model's response is still correct. \n\n"
            "Question: {question}\n\nCorrect Answer: {answer}\n\nModel Response: {response}\n\n"
            "Is the model response correct? Answer yes or no only.")

KNOWLEDGE_UPDATE = ("I will give you a question, a correct answer, and a response from a model. "
                    "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                    "If the response contains some previous information along with an updated answer, "
                    "the response should be considered as correct as long as the updated answer is the "
                    "required answer.\n\nQuestion: {question}\n\nCorrect Answer: {answer}\n\n"
                    "Model Response: {response}\n\nIs the model response correct? Answer yes or no only.")

PREFERENCE = ("I will give you a question, a rubric for desired personalized response, and a response "
              "from a model. Please answer yes if the response satisfies the desired response. Otherwise, "
              "answer no. The model does not need to reflect all the points in the rubric. The response "
              "is correct as long as it recalls and utilizes the user's personal information correctly.\n\n"
              "Question: {question}\n\nRubric: {answer}\n\nModel Response: {response}\n\n"
              "Is the model response correct? Answer yes or no only.")

ABSTENTION = ("I will give you an unanswerable question, an explanation, and a response from a model. "
              "Please answer yes if the model correctly identifies the question as unanswerable. The model "
              "could say that the information is incomplete, or some other information is given but the "
              "asked information is not.\n\nQuestion: {question}\n\nExplanation: {answer}\n\n"
              "Model Response: {response}\n\nDoes the model correctly identify the question as unanswerable? "
              "Answer yes or no only.")

TEMPLATES = {
    "single-session-user": SIMPLE,
    "single-session-assistant": SIMPLE,
    "multi-session": SIMPLE,
    "temporal-reasoning": TEMPORAL,
    "knowledge-update": KNOWLEDGE_UPDATE,
    "single-session-preference": PREFERENCE,
}


def build_prompt(question_type: str, question: str, gold: str, response: str,
                 abstention: bool = False) -> str:
    """The judge prompt exactly as the benchmark builds it."""
    if abstention:
        return ABSTENTION.format(question=question, answer=gold, response=response)
    if question_type not in TEMPLATES:
        raise ValueError(f"unknown question type: {question_type}")
    return TEMPLATES[question_type].format(question=question, answer=gold, response=response)


def verdict(client, question_type: str, question: str, gold: str, response: str,
            abstention: bool = False, max_tokens: int = JUDGE_MAX_TOKENS) -> dict:
    """Ask the judge model and read its verdict.

    Returns the label (``yes`` / ``no`` / ``""``), whether the answer passed
    (true only on an explicit yes), and the reply itself, so a cell can be
    audited after the fact instead of trusted.
    """
    prompt = build_prompt(question_type, question, gold, response, abstention)
    message, usage = client.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)
    raw = str(message.get("content") or "").strip()
    label = parse_label(raw)
    return {
        "label": label,
        "passed": label == "yes",
        "raw": raw,
        "model": client.model,
        "prompt_tokens": int((usage or {}).get("prompt_tokens") or 0),
        "completion_tokens": int((usage or {}).get("completion_tokens") or 0),
    }
