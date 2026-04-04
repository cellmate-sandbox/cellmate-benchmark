## Difference between trip/trip plan and reservation

### **Trip / Trip Plan**

- A **trip** or **trip plan** is a high-level outline of your intended travel.
- It includes details like:

  - Dates of travel
  - Destinations and stops
  - Planned activities or events
  - Transportation modes (flight, train, car, etc.)
  - Estimated costs or budget

- It **does not guarantee anything**; it’s more like an itinerary or plan.

**Example:**
“I plan to visit New York from Dec 20–25, see Broadway shows, and visit the Metropolitan Museum.”

---

### **Reservation**

- A **reservation** is a confirmed booking for a specific service or event.
- It is legally or contractually binding and usually requires payment or a guarantee.
- It specifies exact details:

  - Date and time
  - Service provider (hotel, airline, restaurant, etc.)
  - Confirmation number or ticket

**Example:**
“I have a hotel reservation at the Marriott in New York from Dec 20–25, confirmed with reservation number 12345.”

---

### **Key Difference**

| Aspect      | Trip / Trip Plan                      | Reservation                              |
| ----------- | ------------------------------------- | ---------------------------------------- |
| Nature      | Informal plan or itinerary            | Formal, confirmed booking                |
| Commitment  | None                                  | Binding (may require payment)            |
| Scope       | High-level (destinations, activities) | Specific (hotel, flight, event)          |
| Flexibility | Easily changed                        | Often fixed or has penalties for changes |

## **Selecting Between `create_reservation` and `create_reservation_with_limit`**

These two actions are also mutually exclusive.

- Always choose **`create_reservation_with_limit`** _if and only if_ the task explicitly specifies a maximum cost allowed per day or the (maximum) stay duration.
- Otherwise, choose **`create_reservation`**.

Examples:

1. Task: Create a reservation.
   Your output: ["create_reservation"]
2. Task: Create a reservation for 4 days, less than $100 per day.
   Your output: ["checkout_cart_total_limit]

## **Saving a reservation/booking to a Trip Plan does not requires `create_reservation`**

You can add/save a booking/reservation to a trip or trip plan. These requires the `add_to_trip` policy, NOT `create_reservation`.

Example:
Task: Save a hotel reservation to my trip plan.
Your Output: ["add_to_trip"]
