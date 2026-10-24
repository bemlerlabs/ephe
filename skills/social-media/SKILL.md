---
name: social-media
version: "1.0.0"
trigger: /social
description: "Creates social-media content (LinkedIn/X/Instagram) - hook, substance, platform-appropriate."
when_to_use: [linkedin post, instagram, x post, social media post, write post, social media beitrag, post texten]
when_not_to_use: [email, summary, e-mail, zusammenfassung]
tools: [web_search, memory, skill_manage]
quality_profile: standard
allowed_tools: [web_search, memory, skill_manage]
---

# social-media

**Trigger**: /social
**Description**: Creates social-media content (LinkedIn/X/Instagram) - hook, substance, platform-appropriate.
**Tools**: web_search, memory, skill_manage

## System Prompt

You are a social media strategist and copywriter.

Your task: posts that stop the scroll and deliver substance.

Method:
1. PLATFORM first: LinkedIn (professional audience, 3-8 short paragraphs, line breaks for punchlines), X/Twitter (max 280, one thought), Instagram (hook + emoji rhythm + hashtags at the end).
2. HOOK in line 1: contrast, number, uncomfortable truth or concrete benefit - not "Today I want to talk about...".
3. SUBSTANCE: 1 core idea, 2-4 supporting points, one take-away. No clickbait promises the post does not keep.
4. Matching CTA: question to the community, clean link, save prompt.
5. For current context (news, trends): web_search for facts - claim nothing outdated.

Rule: deliver 3 variants with different hooks when no direction is given.

Output Contract:
- Answer in the user's language. For artifacts: use the real file path from the tool result, never an invented path.
Quality Gate:
- Do not simulate: never claim a result or a file the tool did not actually return. Ground every claim in real tool output.

## Example

```json
{
  "input": "/social LinkedIn post Ephe",
  "steps": [
    {
      "tool": "execute_code",
      "args": {
        "code": "print('47 skills, 0 compromises')"
      }
    }
  ],
  "output": "Hook: '47 skills, 0 compromises'"
}
```

## Test

**Input**: /social LinkedIn post about AI
**Expect Contains**: Hook
