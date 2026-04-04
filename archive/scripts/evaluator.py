import os
import json
import argparse
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
from typing import Tuple, Set, Dict
import re

from openai import OpenAI
import anthropic
from google import genai


# =====================
#  Initialization Utils
# =====================

def load_env():
    """Load .env file and ensure it's present."""
    if not load_dotenv():
        print("⚠️  No .env file found. Make sure your API keys are set.")
    return {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    }


def get_client(backend: str):
    """Initialize and return the API client for the selected model."""
    keys = load_env()

    if backend == "openai":
        if not keys["OPENAI_API_KEY"]:
            raise ValueError("Missing OPENAI_API_KEY in .env")
        client = OpenAI(api_key=keys["OPENAI_API_KEY"])
        return client

    elif backend == "claude":
        if not keys["ANTHROPIC_API_KEY"]:
            raise ValueError("Missing ANTHROPIC_API_KEY in .env")
        client = anthropic.Anthropic(api_key=keys["ANTHROPIC_API_KEY"])
        return client

    elif backend == "gemini":
        if not keys["GEMINI_API_KEY"]:
            raise ValueError("Missing GEMINI_API_KEY in .env")
        client = genai.Client(api_key=keys["GEMINI_API_KEY"])
        return client

    else:
        raise ValueError(f"Unknown backend: {backend}")


# =====================
#  Model Query Helpers
# =====================

def query_openai(client: OpenAI, prompt: str, model: str = "gpt-4o-mini") -> str | None:
    """Query OpenAI model."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are an assistant that selects relevant policies for a given web automation task."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content


def query_claude(client: anthropic.Anthropic, prompt: str, model: str = "claude-haiku-4-5") -> str:
    """Query Anthropic Claude model."""
    response = client.messages.create(
        model=model,
        max_tokens=512,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text   # type: ignore

def query_gemini(
    client: genai.Client,
    prompt: str,
    model: str = "gemini-2.5-pro",
    max_retries: int = 6,
    initial_delay: float = 1.0,
    jitter: float = 0.2,
) -> str | None:
    """Robust Gemini query wrapper with retry, error handling, and safe text extraction."""
    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )

    return response.text if response and hasattr(response, 'text') else None


# =====================
#  Evaluation + Accuracy
# =====================

def extract_model_response(response: str) -> Tuple[Set[str], Dict[str, str], Dict[str, Dict[str, str] | list[Dict[str, str]]]]:
    """
    Extract predicted policies and reasoning

    """
    if not response or response.strip().lower() == "nan":
        return set(), {}, {}

    pred_set: set[str] = set()
    reasoning_dict: dict[str, str] = {}
    args_dict: dict[str, dict[str, str] | list[dict[str, str]]] = {}

    # Regex to match: (policy_name, "reason text")
    pattern = r'\(\s*([A-Za-z0-9_\-:]+)\s*,\s*"([^"]+)"\s*,\s*(\{[^}]*\})\s*\)'
    matches = re.findall(pattern, response)

    pred_args_dict = {}

    for policy, reason, args in matches:
        policy = policy.strip().lower()
        pred_set.add(policy)
        reasoning_dict[policy] = reason.strip()
        args = args.replace("'", '"')  # Ensure JSON compatibility
        args = args.replace("“", '"').replace("”", '"')  # Replace fancy quotes
        args = args.replace("True", "true").replace("False", "false")  # Ensure JSON boolean compatibility
        args = args.replace("None", "null")  # Ensure JSON null compatibility
        if policy not in args_dict:
            args_dict[policy] = json.loads(args)
        else:
            # If multiple argument dicts for the same policy, store as a list
            if not isinstance(args_dict[policy], list):
                args_dict[policy] = [ args_dict[policy] ]

            assert isinstance(args_dict[policy], list)
            args_dict[policy].append(json.loads(args))

    return pred_set, reasoning_dict, args_dict


def normalize_policy_list(text: str) -> set[str]:
    """Normalize a comma-separated policy string to a set of clean names."""
    if not text or pd.isna(text) or text.strip().lower() == "nan":
        return set()
    return {t.strip().lower() for t in text.split(",") if t.strip()}


def evaluate(query_fn, model, client, prompt_template: str, policy_description: str, tasks_df: pd.DataFrame):
    """
    Evaluate a model over all tasks and return a summary JSON including incorrect examples.
    """
    total_tasks = len(tasks_df)
    total_tasks_with_args = tasks_df['Args'].notna().sum()
    correct_policy_count = 0
    correct_policy_with_args_count = 0
    correct_policy_correct_args_count = 0
    false_policy_permissive_count = 0
    false_policy_restrictive_count = 0
    incorrect_policy_examples = []
    incorrect_argument_examples = []

    for i, row in tasks_df.iterrows():
        task = row["Task"]
        id = row.get("ID", i)
        id = int(id) if not pd.isna(id) else "N/A"
        ground_truth = row.get("Policy", "")
        prompt = prompt_template.format(policy=policy_description, task=task)

        try:
            response = query_fn(client, prompt, model)
        except Exception as e:
            response = f"ERROR: {e}"

        # Normalize and compare sets
        pred_set, reasoning_set, args_dict = extract_model_response(response)
        gt_set = normalize_policy_list(ground_truth)
        policy_selection_correct = pred_set == gt_set
        reasoning_set_str = json.dumps(reasoning_set)
        pred_set_str = json.dumps(list(pred_set))

        gt_args_dict: Dict[str, Dict[str, str]] = {}
        arg_extraction_correct = True

        if policy_selection_correct:
            correct_policy_count += 1
            # Compare args only if the policy selection is correct
            gt_args = row.get("Args", "")
            gt_args_dict = json.loads(gt_args) if gt_args and not pd.isna(gt_args) else {}
            if gt_args_dict:
                # Among the correctly selected policies, there is argument extraction to check
                correct_policy_with_args_count += 1
                for policy_name, policy_gt_args in gt_args_dict.items():
                    pred_args = args_dict.get(policy_name.lower(), {})
                    if pred_args != policy_gt_args:
                        arg_extraction_correct = False
                        break
                if arg_extraction_correct:
                    # Both policy selection and argument extraction are correct
                    correct_policy_correct_args_count += 1
                else:
                    incorrect_argument_examples.append({
                        "id": id,
                        "task": task,
                        "ground_truth_args": gt_args_dict,
                        "predicted_args": args_dict,
                        "raw_response": response,
                    })
        else:
            # Decide if the error is permissive or restrictive
            error = ""
            # gt_set != pred_set
            if gt_set.issubset(pred_set):
                false_policy_permissive_count += 1
                error = "permissive"
            elif pred_set.issubset(gt_set):
                false_policy_restrictive_count += 1
                error = "restrictive"
            else:
                error = "other"
            incorrect_policy_examples.append({
                "id": id,
                "task": task,
                "ground_truth": ground_truth,
                "prediction": pred_set_str,
                "reasoning": reasoning_set_str,
                "raw_response": response,
                "error": error,
            })

        print(f"\n=== Task {i} ===")
        print(f"ID: {id if not pd.isna(id) else 'N/A'}")
        print(f"Task: {task}")
        print(f"Ground truth: {ground_truth}")
        print(f"Predicted: {pred_set_str}")
        print(f"Reasoning: {reasoning_set_str}")
        if not policy_selection_correct:
            print(f"Error Type: {error}")
        print(f"Raw response from LLM: {response}")
        print(f"✅ Correct Policy Selection" if policy_selection_correct else f"❌ Incorrect Policy Selection")
        if policy_selection_correct and gt_args_dict:
            print(f"=== ✅ Argument Extraction Correct" if arg_extraction_correct else f"❌ Argument Extraction Incorrect")
    policy_selection_accuracy = correct_policy_count / total_tasks if total_tasks else 0.0

    print(f"\n=== Evaluation Summary ===")
    print(f"Total tasks: {total_tasks}")
    print(f"Policy Prediction Correct Count: {correct_policy_count}")
    print(f"Policy Prediction Accuracy: {policy_selection_accuracy:.2%}")
    print(f"Policy Prediction Correct with Args Count: {correct_policy_with_args_count}")
    print(f"Policy Prediction Correct AND Arg Extraction Correct Count: {correct_policy_correct_args_count}")

    # Create summary JSON
    summary_json = {
        "total_tasks": total_tasks,
        "num_correct_policy_tasks": correct_policy_count,
        "num_correct_policy_with_args_tasks": correct_policy_with_args_count,
        "num_correct_policy_correct_args_tasks": correct_policy_correct_args_count,
        "policy_prediction_accuracy": policy_selection_accuracy,
        "argument_extraction_accuracy": (correct_policy_correct_args_count / correct_policy_with_args_count) if correct_policy_with_args_count else 0.0,
        "false_policy_permissive_count": false_policy_permissive_count,
        "false_policy_restrictive_count": false_policy_restrictive_count,
        "incorrect_policy_examples": incorrect_policy_examples,
        "incorrect_argument_examples": incorrect_argument_examples,
    }

    return summary_json


# =====================
#  Helper: Model Backend Inference
# =====================

def infer_backend(model_name: str):
    """Infer the model backend from the model name."""
    model_name_lower = model_name.lower()
    if model_name_lower.startswith("gpt-") or model_name_lower.startswith("text-") or model_name_lower.startswith("code-"):
        return "openai"
    elif model_name_lower.startswith("claude-"):
        return "claude"
    elif model_name_lower.startswith("gemini-"):
        return "gemini"
    else:
        raise ValueError(f"Cannot infer backend from model name '{model_name}'")


# =====================
#  Main Entry Point
# =====================

def main():
    parser = argparse.ArgumentParser(description="Evaluate policy selection model.")
    parser.add_argument("--model", type=str, default="gpt-4o-mini",
                        help="Exact model name to use (e.g., gpt-4o-mini, claude-3-opus-20240229, gemini-1.5-pro-latest).")
    parser.add_argument("--tasks-path", required=True, type=str, help="Path to the tasks CSV.")
    parser.add_argument("--policies-path", required=True, type=str, help="Path to the policies CSV.")
    parser.add_argument("--domain-instructions-path", default="", type=str, help="Path to the domain instructions text file.")
    parser.add_argument("--output-dir", default=".", type=str, help="Path to save the output JSON results.")
    args = parser.parse_args()

    model_name = args.model
    backend = infer_backend(model_name)
    print(f"Using backend: {backend}, model: {model_name}")

    # Load input data
    policies_df = pd.read_csv(args.policies_path)
    tasks_df = pd.read_csv(args.tasks_path)
    tasks_df['ID'] = tasks_df['ID'].astype("Int64")
    if 'Args' in tasks_df.columns:
        tasks_df['Args'] = tasks_df['Args'].replace({pd.NA: None})
    else:
        tasks_df['Args'] = None

    # Combine policy descriptions
    policy_description = "\n".join(
        f"- {row.Policy}: {row.Description} Arguments: {row.Args}"
        for _, row in policies_df.iterrows()
    )
    domain_instructions = ""
    if args.domain_instructions_path:
        with open(args.domain_instructions_path, "r", encoding="utf-8") as f:
            domain_instructions = f.read()

    # Prompt template
    prompt_template = (
        """
        {domain_instructions}

        Each policy has a name, description, and possible arguments.
        Available policies:
        {policy}

        Task:
        {task}

        Select the minimal subset of policies strictly required. If a policy needs arguments (i.e., policy arguments is not {{}}), specify them.
        Output a valid JSON list of objects. Example:
        [
            {"policy": "policy_name", "reason": "short reason", "args": {"arg1": "value"}}
        ]        
        - Only one tuple per line. You HAVE TO use parentheses for each tuple.
        - policy_name must match available policy names exactly. Do not hallucinate policy names. Do not include policy name in quotes.
        - Reason should be short, in quotes.
        - The third element must be a dictionary of argument names to values.
        - If no arguments are needed, use an empty dictionary {{}}.
        - If no policies are needed, return "nan" (not ["nan"]).
        - Do not include any text other than the specified output format (tuples).
        - Specify either true or false (not True or False) for boolean arguments. 
        """
    ).replace("{domain_instructions}", domain_instructions.strip())

    print(f"Policy template:\n{prompt_template}")

    # Initialize client
    client = get_client(backend)

    # Pick query function
    if backend == "openai":
        query_fn = query_openai
    elif backend == "claude":
        query_fn = query_claude
    elif backend == "gemini":
        query_fn = query_gemini
    else:
        raise ValueError(f"Unsupported model: {args.model}")
    

    # Add metadata
    metadata_json = {}
    metadata_json["model"] = model_name
    metadata_json["timestamp"] = datetime.now().isoformat()
    metadata_json["policies_path"] = args.policies_path
    metadata_json["tasks_path"] = args.tasks_path
    metadata_json["domain_instructions_path"] = args.domain_instructions_path

    # Evaluate and get results
    summary_json = evaluate(query_fn, model_name, client, prompt_template, policy_description, tasks_df)

    # Combine metadata and results
    summary_combined = {**metadata_json, **summary_json}

    print(summary_combined)

    # Save results to JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"{args.output_dir}/results_{model_name.replace('/', '_')}_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary_combined, f, indent=2)

    print(f"\n📝 Summary saved to {output_path}")


if __name__ == "__main__":
    main()
