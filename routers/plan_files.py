import json

from app import mcp
from plan_checks import check_plan
from plan_format import load_plan, plans_dir, save_plan


@mcp.tool()
def plan_check(plan_file: str, fix: bool = False) -> str:
    """
    Check a plan file for implausible values: swim steps over 5 km, steps
    over 6 h, targets over 200% of threshold, workouts over 8 h or TSS 400,
    and steps that don't add up to the planned time. Run it after editing a
    plan and before pushing it.

    Args:
        plan_file: File in the plans directory (TP_PLANS_DIR, default plans/).
        fix: Repair swim distances entered 1000x too large and save the file.
    """
    path = plans_dir() / plan_file
    plan = load_plan(path)
    warnings = check_plan(plan, fix=fix)
    fixed = fix and any("divided by 1000" in w for w in warnings)
    if fixed:
        save_plan(plan, path)
    return json.dumps({"plan": plan.name, "warnings": warnings, "saved_fixes": fixed}, indent=1)
