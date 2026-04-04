import json
import pandas as pd
import argparse

def main(app_type: str):
    # Load final dataset
    final_dataset = pd.read_csv('final_dataset.csv')
    app_data = final_dataset[final_dataset['profile'] == app_type]
    # Save data for the specific app type, for labeling and evaluation purposes
    app_data.to_csv(f'labeled_data/data_{app_type}.csv', index=False)

    # Load app catalog
    with open('catalogs/app_catalog.json') as f:
        app_catalog = json.load(f)
    app_functionalities = app_catalog.get(app_type, [])

    # Load action catalog & Select relevant actions based on app functionalities
    action_catalog = pd.read_csv('catalogs/action_catalog.csv')
    related_actions = action_catalog[action_catalog['Category'].isin(app_functionalities)]

    # Load object catalog & Select relevant objects based on app functionalities
    object_catalog = pd.read_csv('catalogs/object_catalog.csv')
    related_objects = object_catalog[object_catalog['Category'].isin(app_functionalities)].drop(columns=['Source'])

    # Print summary
    print(f"Number of {app_type} tasks: {len(app_data)}")
    print(f"Functionalities of {app_type}: {app_functionalities}")
    print(f"Related actions: {related_actions}")
    print(f"Related objects: {related_objects}")

    # Create prompt template
    prompt_template = (
        """
        Each action has a name and description.
        Available Actions:
        {actions}

        The following objects are relevant to the above actions. You can use it as a reference when determining the necessary actions and their arguments.
        {objects}

        Your goal is to select the minimal subset of actions strictly required. If an action needs arguments (i.e., action arguments is not {{}}), specify them.
        Output as tuples: (action_name, "reason").
        - Only one tuple per line. You HAVE TO use parentheses for each tuple.
        - action_name must match available action names exactly. Do not hallucinate action names. Do not include action name in quotes.
        - Reason should be short, in quotes.
        - If no actions are needed, return "nan" (not ["nan"]).
        - Do not include any text other than the specified output format (tuples).

        Now, perform this task for all the user tasks in the attached dataset.
        """
    ).format(
        actions=str(related_actions),
        objects=str(related_objects),
    )

    # Save prompt template
    with open(f'labeled_data/prompt_template_{app_type}.txt', 'w') as f:
        f.write(prompt_template)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate prompt template for a given app type")
    parser.add_argument("--app-type", type=str, help="Type of the app (e.g., commerce_platform)")
    args = parser.parse_args()
    main(args.app_type)
