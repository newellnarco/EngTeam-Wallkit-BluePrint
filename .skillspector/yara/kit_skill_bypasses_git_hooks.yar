// Custom SkillSpector YARA rules (docs/SCAN_LANE.md, "SkillSpector").
// One rule per confirmed finding. Each rule NAME has a fixture directory
// .skillspector/fixtures/<name>/ holding a sample that must trip it.

rule kit_skill_bypasses_git_hooks {
  meta:
    description = "An agent instruction to skip the git hooks. docs/GIT_HOOKS.md section 3: --no-verify skips every hook invisibly; the named escape hatches exist instead. Added 2026-09-22."
    severity = "high"
  strings:
    $cmd = /git\s+(commit|push|merge|rebase)\b[^\n]{0,80}--no-verify/ nocase
    $cfg = /core\.hooksPath\s*=?\s*\/dev\/null/ nocase
  condition:
    any of them
}
