import gradio as gr
from crewai import Agent, Task, Crew, LLM

# Configure LLM
llm = LLM(
    model="ollama/codellama",
    base_url="http://localhost:11434",
    temperature=0.7
)

# Shared steps log collected via callback
steps_log = []

def step_callback(step):
    """Capture each intermediate agent step."""
    lines = []
    if hasattr(step, "thought") and step.thought:
        lines.append(f"🧠 **Thought:** {step.thought}")
    if hasattr(step, "tool") and step.tool:
        lines.append(f"🔧 **Tool:** {step.tool}")
    if hasattr(step, "tool_input") and step.tool_input:
        lines.append(f"📥 **Input:** {step.tool_input}")
    if hasattr(step, "result") and step.result:
        lines.append(f"📤 **Result:** {step.result}")
    if not lines:
        lines.append(f"📌 **Step:** {str(step)}")
    steps_log.append("\n".join(lines))

# Create persistent Agent with step callback
researcher = Agent(
    role="Research Analyst",
    goal="Answer user queries with detailed analysis",
    backstory="Expert in AI research and technology analysis",
    verbose=True,
    llm=llm,
    step_callback=step_callback
)

THINKING_MSG = "⏳ _Thinking... please wait_"

def run_agent(user_input, history):
    global steps_log
    steps_log = []
    history = history or []

    if user_input.strip().lower() == "quit":
        history = history + [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": "👋 Goodbye! Session ended."}
        ]
        yield history, "", "Session ended."
        return

    # ── Phase 1: immediately echo question + spinner ──────────────────────
    history = history + [
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": THINKING_MSG}
    ]
    yield history, "", "⏳ _Agent is processing..._"

    # ── Phase 2: run the agent ─────────────────────────────────────────────
    task = Task(
        description=user_input,
        expected_output="Detailed summary report",
        agent=researcher
    )

    crew = Crew(
        agents=[researcher],
        tasks=[task],
        verbose=False
    )

    result = crew.kickoff()
    answer = str(result)

    # Format steps summary
    if steps_log:
        steps_md = "\n\n---\n\n".join(
            [f"**Step {i}:**\n{s}" for i, s in enumerate(steps_log, 1)]
        )
    else:
        steps_md = "_No intermediate steps captured for this query._"

    # ── Phase 3: replace spinner with real answer ─────────────────────────
    history[-1] = {"role": "assistant", "content": answer}
    yield history, "", steps_md

def clear_chat():
    return [], "", "_Steps will appear here after each query._"

with gr.Blocks(title="AI Research Agent") as app:
    gr.Markdown("# 🤖 AI Research Agent\nAsk anything. Type **quit** to end the session.")

    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=450, label="Conversation")
            with gr.Row():
                user_input = gr.Textbox(
                    placeholder="Enter your question... (type 'quit' to end)",
                    show_label=False,
                    scale=9
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)
            clear_btn = gr.Button("Clear Chat")

        with gr.Column(scale=1):
            gr.Markdown("### 🪜 Intermediate Steps")
            steps_display = gr.Markdown(
                value="_Steps will appear here after each query._",
                label="Steps"
            )

    send_btn.click(
        fn=run_agent,
        inputs=[user_input, chatbot],
        outputs=[chatbot, user_input, steps_display]
    )
    user_input.submit(
        fn=run_agent,
        inputs=[user_input, chatbot],
        outputs=[chatbot, user_input, steps_display]
    )
    clear_btn.click(fn=clear_chat, outputs=[chatbot, user_input, steps_display])

app.launch()
