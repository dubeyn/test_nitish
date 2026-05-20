import json
import os
import pandas as pd
import gradio as gr
from jira import JIRA, JIRAError

DEFAULT_JIRA_URL = "https://aristocrat.atlassian.net"
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".jira_config.json")


# ─────────────────────────────────────────────
# Credential persistence
# ─────────────────────────────────────────────
def load_credentials():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return (
                data.get("jira_url", DEFAULT_JIRA_URL),
                data.get("email", ""),
                data.get("token", ""),
            )
        except Exception:
            pass
    return DEFAULT_JIRA_URL, "", ""


def save_credentials(jira_url, email, token):
    if not all([jira_url.strip(), email.strip(), token.strip()]):
        return "❌ Fill in all fields before saving."
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(
                {"jira_url": jira_url.strip(), "email": email.strip(), "token": token.strip()},
                f, indent=2
            )
        return f"✅ Credentials saved to `{CONFIG_FILE}`"
    except Exception as e:
        return f"❌ Failed to save: {e}"

# ─────────────────────────────────────────────
# Connect to JIRA
# ─────────────────────────────────────────────
def connect_jira(jira_url: str, email: str, credential: str):
    try:
        client = JIRA(server=jira_url.rstrip("/"), basic_auth=(email, credential))
        me = client.myself()
        return client, None, me.get("displayName", email)
    except JIRAError as e:
        return None, f"JIRA Error {e.status_code}: {e.text}", None
    except Exception as e:
        return None, str(e), None


def test_connection(jira_url, email, credential):
    if not all([jira_url.strip(), email.strip(), credential.strip()]):
        return "❌ Fill in all credential fields first."
    client, err, name = connect_jira(jira_url.strip(), email.strip(), credential.strip())
    if err:
        msg = f"❌ {err}\n\n"
        if "401" in str(err):
            msg += (
                "**Troubleshooting 401 tips:**\n"
                "- Use your **Atlassian account email**, not display name\n"
                "- API token must be generated at https://id.atlassian.com/manage-profile/security/api-tokens\n"
                "- Try without `/jira` in the URL (e.g. `https://aristocrat.atlassian.net`)\n"
                "- If org uses **SSO/SAML**, ask IT admin to allow API token access\n"
                "- Some orgs require a **Personal Access Token (PAT)** — check with your admin"
            )
        return msg
    return f"✅ Connected as **{name}**"


# ─────────────────────────────────────────────
# Search JIRA bugs
# ─────────────────────────────────────────────
COLS = ["Key", "Summary", "Status", "Priority", "Assignee", "Created"]
PAGE_SIZE = 10


def get_page_slice(full_df, page):
    total = len(full_df)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    sliced = full_df.iloc[start:start + PAGE_SIZE]
    info = f"📊 **{total} issue(s) found** — Page {page + 1} of {total_pages}"
    return sliced, info


def go_prev(full_df, page):
    new_page = max(0, page - 1)
    sliced, info = get_page_slice(full_df, new_page)
    return sliced, new_page, info


def go_next(full_df, page):
    total = len(full_df)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    new_page = min(total_pages - 1, page + 1)
    sliced, info = get_page_slice(full_df, new_page)
    return sliced, new_page, info


def search_bugs(jira_url, email, credential, search_text, issue_type, max_results, parent, component, platform):
    empty = pd.DataFrame(columns=COLS)
    if not email.strip() or not credential.strip():
        return empty, "❌ Please enter your credentials.", "", empty, 0, ""

    has_filter = any([
        search_text.strip(),
        issue_type != "Any",
        parent and parent.strip(),
        component and component.strip(),
        platform and platform.strip(),
    ])
    if not has_filter:
        return empty, "❌ Enter at least one filter (search text, issue type, parent, component, or platform).", "", empty, 0, ""

    client, err, _ = connect_jira(jira_url.strip(), email.strip(), credential.strip())
    if err:
        return empty, f"❌ Connection failed: {err}", "", empty, 0, ""

    conditions = ['project in ("NM", "META", "CAT")']
    if search_text.strip():
        wildcard_term = " ".join(w + "*" for w in search_text.strip().split())
        conditions.append(f'text ~ "{wildcard_term}"')
    if issue_type != "Any":
        conditions.append(f'issuetype = "{issue_type}"')
    if parent and parent.strip():
        conditions.append(f'parent = "{parent.strip()}"')
    if component and component.strip():
        conditions.append(f'component = "{component.strip()}"')
    if platform and platform.strip():
        conditions.append(f'"Platform" = "{platform.strip()}"')

    jql = " AND ".join(conditions) + " ORDER BY created DESC"

    try:
        issues = client.search_issues(jql, maxResults=int(max_results))
    except JIRAError as e:
        return empty, f"❌ JQL Error: {e.text}", jql, empty, 0, ""

    if not issues:
        return empty, f"⚠️ No issues found.", jql, empty, 0, ""

    rows = []
    for issue in issues:
        rows.append([
            issue.key,
            issue.fields.summary,
            issue.fields.status.name,
            getattr(issue.fields.priority,  "name",        "—"),
            getattr(issue.fields.assignee,  "displayName", "Unassigned"),
            issue.fields.created[:10],
        ])

    df = pd.DataFrame(rows, columns=COLS)
    first_page, page_info = get_page_slice(df, 0)
    return first_page, "✅ Click a **Key** to preview", jql, df, 0, page_info


def preview_issue(jira_url, email, credential, issue_key):
    if not issue_key or not issue_key.strip():
        return "_Click an issue key in the results to preview details._"
    if not email.strip() or not credential.strip():
        return "❌ Enter credentials first."
    client, err, _ = connect_jira(jira_url.strip(), email.strip(), credential.strip())
    if err:
        return f"❌ {err}"
    try:
        issue = client.issue(issue_key.strip())
    except JIRAError as e:
        return f"❌ {e.text}"

    key      = issue.key
    summary  = issue.fields.summary
    status   = issue.fields.status.name
    priority = getattr(issue.fields.priority, "name",        "—")
    assignee = getattr(issue.fields.assignee, "displayName", "Unassigned")
    reporter = getattr(issue.fields.reporter, "displayName", "—")
    created  = issue.fields.created[:10]
    updated  = issue.fields.updated[:10]
    desc     = getattr(issue.fields, "description", "") or "_No description provided._"
    if len(desc) > 800:
        desc = desc[:800] + "…"
    url = f"{jira_url.rstrip('/')}/browse/{key}"

    return (
        f"### [{key}]({url}) — {summary}\n\n"
        f"| Field | Value |\n|---|---|\n"
        f"| **Status** | {status} |\n"
        f"| **Priority** | {priority} |\n"
        f"| **Assignee** | {assignee} |\n"
        f"| **Reporter** | {reporter} |\n"
        f"| **Created** | {created} |\n"
        f"| **Updated** | {updated} |\n\n"
        f"**Description:**\n\n{desc}\n\n"
        f"[🔗 Open in JIRA]({url})"
    )


def on_select(jira_url, email, credential, evt: gr.SelectData):
    if evt.index[1] != 0:
        return "_Click on an issue **key** (first column) to preview it._"
    return preview_issue(jira_url, email, credential, str(evt.value))


def clear_credentials():
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
        return DEFAULT_JIRA_URL, "", "", "✅ Saved credentials deleted."
    return DEFAULT_JIRA_URL, "", "", "ℹ️ No saved credentials found."


TOKEN_GUIDE = """
### 🔑 How to get a free API Token
1. Go to 👉 [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **"Create API token"**
3. Give it any label (e.g. `VSCode`) and click **Create**
4. Copy the token and paste it in the field above

> ⚠️ Use your **Atlassian account email** (same as login), not your display name.  
> ⚠️ If your org uses SSO and blocks API tokens, ask IT to enable it.
"""


# ─────────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────────
_saved_url, _saved_email, _saved_token = load_credentials()
_has_saved = bool(_saved_email)

with gr.Blocks(title="JIRA Bug Search") as app:
    gr.Markdown("# 🐛 JIRA Bug Search")

    # ── Shared Credentials (visible from all tabs) ──────────────
    with gr.Accordion("🔑 Credentials", open=not _has_saved):
        if _has_saved:
            gr.Markdown(f"✅ **Loaded:** `{_saved_email}` — edit and re-save any time.")
        with gr.Row():
            jira_url_input = gr.Textbox(label="JIRA URL",   value=_saved_url,   placeholder="https://yourcompany.atlassian.net", scale=2)
            email_input    = gr.Textbox(label="Email",       value=_saved_email, placeholder="you@aristocrat.com", scale=2)
            token_input    = gr.Textbox(label="API Token",   value=_saved_token, placeholder="Paste token here", type="password", scale=2)
        with gr.Row():
            test_btn  = gr.Button("🔌 Test Connection", size="sm")
            save_btn  = gr.Button("💾 Save",            size="sm")
            clear_btn = gr.Button("🗑️ Delete Saved",    size="sm", variant="stop")
        with gr.Accordion("📖 How to get an API Token", open=False):
            gr.Markdown(TOKEN_GUIDE)
        conn_status = gr.Markdown(value="")

    # ── Search ───────────────────────────────
    with gr.Row():
        with gr.Column(scale=1):
            search_input = gr.Textbox(label="Search text", placeholder="e.g. crash, login, null pointer")
            gr.Markdown("_Projects: **NM**, **META**, **CAT**_")
            issue_type   = gr.Dropdown(
                label="Issue type",
                choices=["Any", "Bug", "Task", "Story", "Epic", "Sub-task"],
                value="Bug"
            )
            max_results  = gr.Slider(label="Max results", minimum=5, maximum=50, value=10, step=5)
            with gr.Row():
                parent_input    = gr.Textbox(label="Parent (optional)",    placeholder="e.g. NM-1234",  scale=1)
                component_input = gr.Textbox(label="Component (optional)", placeholder="e.g. Frontend", scale=1)
                platform_input  = gr.Textbox(label="Platform (optional)",  placeholder="e.g. iOS",      scale=1)
            search_btn   = gr.Button("🔍 Search", variant="primary", size="lg")

        with gr.Column(scale=2):
            gr.Markdown("### 📋 Results  _(click a Key cell to preview)_")
            search_status = gr.Markdown(value="")
            page_info     = gr.Markdown(value="")
            results_df    = gr.Dataframe(headers=COLS, datatype=["str"]*6, interactive=False, wrap=True)
            with gr.Row():
                prev_btn  = gr.Button("◀ Prev", size="sm", scale=1)
                next_btn  = gr.Button("Next ▶", size="sm", scale=1)
            gr.Markdown("### 👁️ Issue Preview")
            preview_md    = gr.Markdown(value="_Click an issue key in the table above._")
            gr.Markdown("### 📝 JQL Used")
            jql_box       = gr.Textbox(label="", interactive=False, lines=2)

    # ── State ──────────────────────────────────────
    all_results_state = gr.State(pd.DataFrame(columns=COLS))
    page_state        = gr.State(0)

    # ── Event handlers ─────────────────────────────
    test_btn.click(fn=test_connection,  inputs=[jira_url_input, email_input, token_input], outputs=[conn_status])
    save_btn.click(fn=save_credentials, inputs=[jira_url_input, email_input, token_input], outputs=[conn_status])
    clear_btn.click(fn=clear_credentials, outputs=[jira_url_input, email_input, token_input, conn_status])

    _search_inputs  = [jira_url_input, email_input, token_input, search_input, issue_type, max_results, parent_input, component_input, platform_input]
    _search_outputs = [results_df, search_status, jql_box, all_results_state, page_state, page_info]
    search_btn.click(fn=search_bugs,   inputs=_search_inputs, outputs=_search_outputs)
    search_input.submit(fn=search_bugs, inputs=_search_inputs, outputs=_search_outputs)

    prev_btn.click(fn=go_prev, inputs=[all_results_state, page_state], outputs=[results_df, page_state, page_info])
    next_btn.click(fn=go_next, inputs=[all_results_state, page_state], outputs=[results_df, page_state, page_info])

    results_df.select(fn=on_select, inputs=[jira_url_input, email_input, token_input], outputs=[preview_md])

if __name__ == "__main__":
    import socket
    host = socket.gethostbyname(socket.gethostname())
    print(f"\n🔗 Share this with your team: http://{host}:7861\n")
    app.launch(server_name="0.0.0.0", server_port=7861)
