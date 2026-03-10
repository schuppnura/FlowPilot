# Operating Manual  
## Warp + Cursor + VS Code for Python-Heavy Development

**Objective**  
Maintain high-quality AI assistance over long sessions by strictly controlling context scope, verbosity, and responsibility boundaries.

---

## 1. Tool Responsibilities (Non-Negotiable)

### Warp — Execution Surface
Purpose:
- Command execution
- Environment interaction
- Running tests, linters, builds

Allowed:
- `uv`, `pip`, `pytest`, `ruff`, `mypy`, `make`
- Short outputs only

Prohibited:
- AI reasoning loops
- Pasting large logs or files
- Long-lived debugging sessions

Rule:
- Warp tabs are disposable.

---

### Cursor — Local AI Reasoning
Purpose:
- File- or selection-scoped code changes
- Refactors, explanations, test generation

Allowed:
- Explicit code selections
- Single, concrete instructions
- One task per prompt

Prohibited:
- “Understand the whole project”
- Multi-step reasoning chains
- Long chat histories

Rule:
- Always select code before invoking AI.

---

### VS Code — System of Record
Purpose:
- Navigation and comprehension
- Git diffs and reviews
- Final authority on correctness

Allowed:
- Manual reasoning
- Search, blame, diff
- Review before commit

Rule:
- AI output is untrusted until reviewed here.

---

## 2. Warp Tab Discipline

### One Task = One Tab
Examples:
- Run tests
- Package CLI
- Build Docker image

When task completes:
- Close the tab
- Open a new one

---

### Mandatory Tab Reset Triggers
Open a new Warp tab immediately if:
- Context < 25%
- Verbose output was produced
- Logs exceed one screen
- You switch problem domains

---

### Output Hygiene
Never debug from raw terminal output.

Instead:
```bash
pytest tests/test_auth.py > failure.txt
```

Review in VS Code. Extract only the relevant excerpt for AI.

---

## 3. Cursor Prompting Rules

### Selection-First Rule
Every AI prompt must have:
- An explicit selection
- A single, bounded objective

Example:
> “Refactor this function to remove duplication and comply with these rules: no nested functions, explicit variable names.”

---

### One-Shot Principle
Preferred:
- One prompt
- Apply changes
- Manual review

If iteration is required:
- Close the chat
- Re-select updated code
- Start a new prompt

---

### Constraint Restatement
Never rely on memory.

Always restate:
- Naming rules
- CLI structure
- Error-handling standards

Tokens are cheaper than rework.

---

## 4. AI Exclusion Zones

Do **not** use AI for:
- Cross-project reasoning
- Root-cause analysis from logs alone
- Reviewing its own changes
- Implicit architectural decisions

AI assists. You decide.

---

## 5. Standard Work Loop

Repeat this loop continuously:

1. **Think** (VS Code)
2. **Edit** (Cursor)
3. **Run** (Warp)
4. **Review** (VS Code)
5. **Reset**

---

## 6. Quality Signals

You are operating correctly if:
- Warp context rarely drops below 50%
- Cursor changes converge in 1–2 passes
- Diffs are small and readable
- AI explanations are unnecessary
- You trust reviews, not chat history

---

## 7. Institutional Memory (Optional)

Encode standards in artifacts:
- `README.md`
- `CONTRIBUTING.md`

Reference them explicitly in prompts to externalize context.

---

**Final Rule**  
If AI quality degrades, reset first. Never argue with a saturated context window.
