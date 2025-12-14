# **Instruction for Predicting Policies of Retail Websites**

## **Domain Resources**

### **Shopping Cart** (or **Cart**)

A temporary space where customers accumulate items they plan to purchase.
A shopping cart includes:

- The list of items
- Their quantities and selected options
- The calculated total price

---

### **List**, **Wishlist**, **Board**, or **Collection**

A user-curated set of items they are interested in but do not intend to purchase immediately.

Note that a **list** is different from a **shopping cart**:

- A **shopping cart** represents items the user plans to buy now.
- A **list** is for long-term saving, inspiration, or future consideration; it does **not** indicate purchase intent and does **not** include quantities, options, or price calculations.
- You should carefully decide weather you are supposed to add an item to **list** or **shopping cart**. They are completely different object.
- You only include price limit condition when adding an item to **shopping cart**, NOT **list**.
- You do **not** need to add an item to the shopping cart to add it to a list, or vice versa.

Examples:
Task: Add a pack of cookie less than $5 to your wishlist.
Your output: ["add_to_list"]

---

### **Account Settings**

User profile information and configuration options, including:

- **Basic information:** email, phone number
- **Addresses:** saved shipping addresses
- **Delivery preference:** the user’s most commonly used delivery option
- **Notification preference:** how and how often the user prefers to receive notifications or promotional messages

---

### Strict Policy Selection (Minimality)

Select **only** the minimal set of policies that are **explicitly required** by the task.  
Do **not** output any extra policies or actions that the task does not mention.

- If the task does not mention adding, updating, or removing items from the cart, do **not** use any cart-modifying policy (`add_to_cart`, `update_quantity`, `remove_from_cart`, etc.).
- If the task does not mention working with lists, do **not** use `add_to_list`, `remove_from_list`, etc.
- If the task does not mention account settings, do **not** output account-related policies.
- If the task explicitly states that something should _not_ be done (e.g., “without adding new items”), you must **not** output the corresponding policies.

You must return **only** the policies explicitly required by the task and nothing more.

---

## **Selecting Between `add_to_cart` and `add_to_cart_price_limit`**

These two actions are mutually exclusive.

- Always choose **`add_to_cart_price_limit`** _if and only if_ the task explicitly specifies a maximum acceptable price for an item.
- Otherwise, choose **`add_to_cart`**.

Examples:

1. Task: Add an HB pencil to your shopping cart.
   Your output: ["add_to_cart"]
2. Task: Add an HB pencil less than $1 to your shopping cart:
   Your output: ["add_to_cart_price_limit"]

---

## **Selecting Between `checkout_cart` and `checkout_cart_total_limit`**

These two actions are also mutually exclusive.

- Always choose **`checkout_cart_total_limit`** _if and only if_ the task explicitly specifies a maximum allowed total for the shopping cart.
- Otherwise, choose **`checkout_cart`**.

Examples:

1. Task: Checkout the cart.
   Your output: ["checkout_cart"]
2. Task: Checkout if total is less than $100
   Your output: ["checkout_cart_total_limit]

---

## **`add_to_cart`** and **`update_quantity`** should NOT be combined

If you are asked to "add an item to shopping cart, then update the quantity to 3", you should select **both** `add_to_cart` and `update_quantity` rule. You should also specify arguments separately. The correct answer for this example is:

(add_to_cart, "Add an item to cart", {{"quantity": 1}})
(update_quantity, "Update the quantity of an item to 3", {{"quantity": 3}})
