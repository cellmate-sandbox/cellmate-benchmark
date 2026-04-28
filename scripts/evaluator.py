import json
import pandas as pd
import argparse
import re
from typing import Tuple, Set, Dict
from datetime import datetime

from openai import OpenAI
import anthropic
from google import genai
from dotenv import load_dotenv
import os


# =====================
#  Initialization Utils
# =====================

def load_env():
    """Load environment variables from .env file and return API keys."""
    if not load_dotenv():
        print("⚠️  No .env file found. Make sure your API keys are set.")
    return {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    }


def get_client(backend: str):
    """Instantiate and return the API client for the given backend."""
    keys = load_env()
    if backend == "openai":
        if not keys["OPENAI_API_KEY"]:
            raise ValueError("Missing OPENAI_API_KEY in .env")
        return OpenAI(api_key=keys["OPENAI_API_KEY"])
    elif backend == "claude":
        if not keys["ANTHROPIC_API_KEY"]:
            raise ValueError("Missing ANTHROPIC_API_KEY in .env")
        return anthropic.Anthropic(api_key=keys["ANTHROPIC_API_KEY"])
    elif backend == "gemini":
        if not keys["GEMINI_API_KEY"]:
            raise ValueError("Missing GEMINI_API_KEY in .env")
        return genai.Client(api_key=keys["GEMINI_API_KEY"])
    else:
        raise ValueError(f"Unknown backend: {backend}")


def infer_backend(model_name: str) -> str:
    """Infer the API backend (openai / claude / gemini) from the model name prefix."""
    m = model_name.lower()
    if m.startswith("gpt-") or m.startswith("text-") or m.startswith("code-"):
        return "openai"
    elif m.startswith("claude-"):
        return "claude"
    elif m.startswith("gemini-"):
        return "gemini"
    else:
        raise ValueError(f"Cannot infer backend from model name '{model_name}'")


# =====================
#  Model Query Helpers
# =====================

def query_openai(client: OpenAI, prompt: str, model: str = "gpt-4o-mini") -> str:
    """Send a prompt to an OpenAI model and return the text response."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are an assistant that selects relevant actions for a given web automation task."},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content or ""


def query_claude(client: anthropic.Anthropic, prompt: str, model: str = "claude-haiku-4-5") -> str:
    """Send a prompt to an Anthropic Claude model and return the text response."""
    response = client.messages.create(
        model=model,
        max_tokens=512,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text  # type: ignore


def query_gemini(client: genai.Client, prompt: str, model: str = "gemini-2.5-pro") -> str:
    """Send a prompt to a Google Gemini model and return the text response."""
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text if response and hasattr(response, "text") else ""


# Maps each backend name to its query function for easy dispatch in main.
QUERY_FNS = {
    "openai": query_openai,
    "claude": query_claude,
    "gemini": query_gemini,
}


# =====================
#  Response Parsing
# =====================

def extract_model_response(response: str) -> Tuple[Set[str], Dict[str, str]]:
    if not response or response.strip().lower() == "nan":
        return set(), {}

    pred_set: Set[str] = set()
    reasoning_dict: Dict[str, str] = {}

    # Updated pattern to handle escaped quotes within the reasoning string
    pattern = r'\(\s*([A-Za-z0-9_\-:]+)\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)'
    
    for action, reason in re.findall(pattern, response):
        action = action.strip().lower()
        pred_set.add(action)
        # Optional: Clean up the backslashes in the stored reasoning
        reasoning_dict[action] = reason.strip().replace('\\"', '"')

    return pred_set, reasoning_dict

def normalize_action_list(text: str) -> Set[str]:
    """
    Normalize the required_actions column value to a set of lowercase action names.
    Handles Python list literals (e.g. "['add_to_cart', 'checkout']") and
    plain comma-separated strings.
    """
    if not text or isinstance(text, float):
        return set()
    text = str(text).strip()

    # Try to extract items from a Python list literal first
    items = re.findall(r"'([^']+)'", text)
    if items:
        return {item.strip().lower() for item in items}

    # Fallback: treat as a plain comma-separated string
    return {t.strip().lower() for t in text.split(",") if t.strip()}


# =====================
#  Per-task Querying + Evaluation
# =====================

def query_and_evaluate(
    app_data: pd.DataFrame,
    prompt_template: str,
    query_fn,
    client,
    model: str,
) -> Tuple[pd.DataFrame, dict]:
    """
    Iterate over every row in app_data, query the model with a per-task prompt,
    compare predictions against the required_actions ground truth, and return:
      - an annotated DataFrame with predicted_actions, reasoning, raw_response,
        is_correct, and error_type columns appended to the original rows
      - a summary dict with aggregate accuracy metrics and incorrect examples
    """
    results = []
    correct_count = 0
    false_permissive_count = 0   # model predicted a superset of the ground truth
    false_restrictive_count = 0  # model predicted a subset of the ground truth
    incorrect_examples = []

    for i, row in app_data.iterrows():
        task = row.get("task", "")
        task_id = row.get("index", i)
        ground_truth_raw = row.get("actions", "")
        gt_set = normalize_action_list(ground_truth_raw)

        # Append the specific task to the shared context prompt
        per_task_prompt = prompt_template + f"\nTask:\n{task}"

        # print("++++++++++++++++++++++++++++++++++")
        # print("Prompt:", per_task_prompt)
        # print("++++++++++++++++++++++++++++++++++")

        try:
            response = query_fn(client, per_task_prompt, model)
        except Exception as e:
            response = f"ERROR: {e}"

        print("Raw model response:", response)

        pred_set, reasoning_dict = extract_model_response(response)
        is_correct = pred_set == gt_set

        # Classify the type of error when the prediction is wrong
        error_type = ""
        if is_correct:
            correct_count += 1
        else:
            if gt_set.issubset(pred_set):
                # All required actions were predicted, but extras were included
                false_permissive_count += 1
                error_type = "permissive"
            elif pred_set.issubset(gt_set):
                # Only a subset of required actions was predicted
                false_restrictive_count += 1
                error_type = "restrictive"
            else:
                # Predicted and ground-truth sets overlap only partially (or not at all)
                error_type = "other"
            incorrect_examples.append({
                "id": task_id,
                "task": task,
                "ground_truth": list(gt_set),
                "predicted": list(pred_set),
                "reasoning": reasoning_dict,
                "raw_response": response,
                "error_type": error_type,
            })

        print(f"\n=== Task {i} (ID: {task_id}) ===")
        print(f"Task: {task}")
        print(f"Ground truth: {gt_set}")
        print(f"Predicted:    {pred_set}")
        print(f"Reasoning:    {reasoning_dict}")
        print(f"{'✅ Correct' if is_correct else f'❌ Incorrect ({error_type})'}")

        results.append({
            **row.to_dict(),
            "predicted_actions": json.dumps(list(pred_set)),
            "reasoning": json.dumps(reasoning_dict),
            "raw_response": response,
            "is_correct": is_correct,
            "error_type": error_type,
        })

    total = len(app_data)
    accuracy = correct_count / total if total else 0.0

    summary = {
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "total_tasks": total,
        "correct_count": correct_count,
        "accuracy": accuracy,
        "false_permissive_count": false_permissive_count,
        "false_restrictive_count": false_restrictive_count,
        "incorrect_examples": incorrect_examples,
    }

    print(f"\n=== Evaluation Summary ===")
    print(f"Total tasks:       {total}")
    print(f"Correct:           {correct_count}")
    print(f"Accuracy:          {accuracy:.2%}")
    print(f"False permissive:  {false_permissive_count}")
    print(f"False restrictive: {false_restrictive_count}")

    return pd.DataFrame(results), summary


# =====================
#  Main Entry Point
# =====================

def main(data_path: str, model_name: str):
    backend = infer_backend(model_name)
    print(f"Using backend: {backend}, model: {model_name}")

    # Load the pre-filtered app dataset from the provided path
    app_data = pd.read_csv(data_path)

    # All rows must belong to the same app profile; mixed files are not supported
    profiles = app_data["profile"].unique()
    if len(profiles) != 1:
        raise ValueError(f"Expected all rows to have the same profile, found: {profiles.tolist()}")
    app_type = profiles[0]
    print(f"Loaded {len(app_data)} tasks from {data_path} (app_type: {app_type})")

    # Load the app catalog to find which functional categories this app covers
    with open("../data/catalogs/app_catalog.json") as f:
        app_catalog = json.load(f)
    app_functionalities = app_catalog.get(app_type, [])

    # Filter the action catalog to only the categories relevant to this app
    action_catalog = pd.read_csv("../data/catalogs/action_catalog.csv")
    related_actions = action_catalog[action_catalog["Category"].isin(app_functionalities)]
    action_str = "\n".join(related_actions.apply(lambda row: f"{row['Action']}: {row['Description']}", axis=1).tolist())

    # Filter the object catalog similarly and drop the internal Source column
    object_catalog = pd.read_csv("../data/catalogs/object_catalog.csv")
    related_objects = object_catalog[object_catalog["Category"].isin(app_functionalities)].drop(columns=["Source"])
    object_str = "\n".join(related_objects.apply(lambda row: f"{row['Object']}: {row['Definition']}", axis=1).tolist())

    print(f"Functionalities of {app_type}: {app_functionalities}")
    print(f"Related actions:\n{related_actions}")
    print(f"Related objects:\n{related_objects}")

    # Build the shared portion of the prompt; the individual task is appended per row
    # at query time inside query_and_evaluate.
    prompt_template = (
        """
        Each action has a name and description.
        Available Actions:
        {actions}

        The following objects are relevant to the above actions. You can use it as a reference when determining the necessary actions and their arguments.
        {objects}

        Your goal is to select the minimal subset of actions strictly required.
        Output as tuples: (action_name, "reason").
        - Only one tuple per line. You HAVE TO use parentheses for each tuple.
        - action_name must match available action names exactly. Do not hallucinate action names. Do not include action name in quotes.
        - Reason should be short, in quotes.
        - If no actions are needed, return "nan" (not ["nan"]).
        - Do not include any text other than the specified output format (tuples).
        """
    ).format(
        actions=action_str,
        objects=object_str,
    )

    # Initialize the model client and select the matching query function
    client = get_client(backend)
    query_fn = QUERY_FNS[backend]

    results_df, summary = query_and_evaluate(app_data, prompt_template, query_fn, client, model_name)

    # Save outputs to the same directory as the input file
    output_dir = os.path.dirname(os.path.abspath(data_path))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_model = model_name.replace("/", "_")

    # csv_path = os.path.join(output_dir, f"results_{app_type}_{safe_model}_{timestamp}.csv")
    # results_df.to_csv(csv_path, index=False)
    # print(f"📝 Results saved to {csv_path}")

    json_path = os.path.join(output_dir, f"summary_{app_type}_{safe_model}_{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"📊 Summary saved to {json_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query model and evaluate action predictions for app data")
    parser.add_argument("--path", type=str, required=True, help="Path to the app_data CSV file")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="Model name to use")
    args = parser.parse_args()
    main(args.path, args.model)