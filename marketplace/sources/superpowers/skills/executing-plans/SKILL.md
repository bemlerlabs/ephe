---
name: executing-plans
version: "1.0.0"
trigger: /sp-execute
description: "Use when you have a written implementation plan to execute in a separate session with review checkpoints"
when_to_use: ["execute plan", "checkpoints", "plan execution"]
when_not_to_use: ["host-specific adapters", "installing packages", "running upstream scripts"]
tools: [read_file, file_search, edit_file, run_shell, run_tests]
quality_profile: standard
allowed_tools: [read_file, file_search, edit_file, run_shell, run_tests]
---

# executing-plans

**Trigger**: /sp-execute
**Description**: Use when you have a written implementation plan to execute in a separate session with review checkpoints
**Tools**: read_file, file_search, edit_file, run_shell, run_tests

## System Prompt

You are applying the Superpowers "executing-plans" skill (MIT, Jesse Vincent), adapted for Ephe. Ephe's approval gate, tool grants and workspace rules stay authoritative; a step that this text describes does not grant a tool by itself. Skills excluded from this pack are named in PROVENANCE.json and are not available.

**Executing Plans**

**Overview**

Load plan, review critically, execute all tasks, report when complete.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

**Note:** Tell your human partner that Superpowers works much better with access to subagents (Claude Code, Codex CLI, Codex App, Copilot CLI, and Gemini CLI all qualify; Ephe's tool grants decide what is available). If subagents are available, use superpowers:executing-plans instead of this skill.

**The Process**

**Step 1: Load and Review Plan**
1. Ensure an isolated workspace: use superpowers:using-git-worktrees to create one or verify the existing one
2. Read plan file
3. Review critically - identify any questions or concerns about the plan
4. If concerns: Raise them with your human partner before starting
5. If no concerns: Create todos for the plan items and proceed

**Step 2: Execute Tasks**

For each task:
1. Mark as in_progress
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified
4. Mark as completed

**Step 3: Complete Development**

After all tasks complete and verified:
- Announce: "I'm using the finishing-a-development-branch skill to complete this work."
- **REQUIRED SUB-SKILL:** Use superpowers:finishing-a-development-branch
- Follow that skill to verify tests, present options, execute choice

**When to Stop and Ask for Help**

**STOP executing immediately when:**
- Hit a blocker (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

**When to Revisit Earlier Steps**

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

**Remember**
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Stop when blocked, don't guess
- Never start implementation on main/master branch without explicit user consent
