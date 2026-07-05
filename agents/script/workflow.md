# Script Agent Workflow

## Step 1 — Load Input

Read the latest research output.

Source:

```
agents/research/output/<channel>/latest.json
```

Validate the input before processing.

---

## Step 2 — Select Idea

Choose the target content idea.

If no specific idea is provided, select the highest-ranked idea.

---

## Step 3 — Generate Script

Create a production-ready long-form YouTube script.

The script should include:

- Hook
- Introduction
- Main Sections
- Conclusion
- Call To Action

---

## Step 4 — Validate Output

Ensure the generated output follows the required schema.

Reject invalid responses.

---

## Step 5 — Save Output

Update:

```
latest.json
```

Create an archived copy using a timestamp.

---

## Step 6 — Finish

Return the generated JSON.

Log successful execution.