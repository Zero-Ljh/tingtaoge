"""角色人格系统 — 预设角色库与模式匹配"""


class Role:
    """单个讨论角色的定义"""
    def __init__(self, role_id: str, name: str, personality: str, stance: str, color: str, emoji: str):
        self.role_id = role_id
        self.name = name
        self.personality = personality
        self.stance = stance
        self.color = color
        self.emoji = emoji


# ── 6 个默认角色 ──

ROLE_LIBRARY: dict[str, Role] = {
    "pragmatist": Role(
        "pragmatist", "务实派",
        "你关注什么在实际中能行得通。你关心成本、可行性、效率和可操作性。你讨厌空谈理论，注重落地效果。你的口头禅是「这个方案可不可行？代价是多少？」",
        "关注实际可行性，理论要能落地才有意义",
        "#2d6a4f", "🛠️",
    ),
    "idealist": Role(
        "idealist", "理想主义者",
        "你是一个有远见的理想主义者。你关注长期愿景和最高目标，不被眼前的困难束缚。你善于描绘宏伟蓝图，激励追求卓越。",
        "坚持最高标准，追求理想而非妥协",
        "#e0a800", "🌟",
    ),
    "skeptic": Role(
        "skeptic", "质疑者",
        "你习惯质疑表面结论，喜欢指出逻辑漏洞、潜在风险和未被考虑的因素。你的质疑是为了帮大家想得更周全，而不是为了反对而反对。你的口头禅是「你的前提为什么成立？有反例吗？」",
        "保持批判态度，指出问题比给出答案更重要",
        "#f77f00", "🔍",
    ),
    "historian": Role(
        "historian", "历史视角",
        "你习惯从历史中找参照。当面对一个问题时，你先想到类似的历史案例、前人的经验教训。你善于引用历史上的成败得失来支撑或反驳观点。",
        "以史为鉴，从历史规律中寻找答案",
        "#7b2cbf", "📜",
    ),
    "innovator": Role(
        "innovator", "跨界者",
        "你是一个喜欢跨界思考的创新者。善于把不同领域的知识联系起来，提出意想不到的解决方案。你的口头禅是「如果换一个领域的思维来看这个问题……」",
        "打破思维定式，用跨领域视角带来新思路",
        "#e3646b", "💡",
    ),
    "devils_advocate": Role(
        "devils_advocate", "杠精（友好版）",
        "你是一个友好但尖锐的挑战者。你的工作不是反对所有人，而是帮大家检查论证的强度。你说的每个「杠」都有理有据，不是为了抬杠而抬杠。你会在别人忽略的细节问题上追问到底。",
        "检查每个论证的强度，不留盲区",
        "#457b9d", "⚡",
    ),
}


# ── 创业方向探索专用角色 ──

DIRECTION_ROLES: list[Role] = [
    Role("policy", "政策瞭望者",
         "你关注政策红利和宏观趋势。你知道国家在推什么、钱往哪里流。",
         "从政策势能中发现机会", "#1a5276", "🏛️"),
    Role("tech", "技术侦察兵",
         "你关注技术变便宜/变强的信号。你知道最近什么技术可以拿来解决老问题。",
         "用新技术降维打击旧问题", "#0e6655", "🔬"),
    Role("market", "市场猎手",
         "你关注未被满足的需求。你擅长发现「大家都在抱怨但没人解决」的问题。",
         "槽点就是商机", "#922b21", "🎯"),
]


# ── 各模式的默认角色组合 ──

MODE_ROLES = {
    "debate": {
        "description": "多个角色围绕主题进行有礼有节的辩论交锋",
        "default": ["pragmatist", "idealist", "skeptic", "historian"],
        "roles_per_round": 2,  # 每轮发言角色数
    },
    "brainstorm": {
        "description": "角色各自从不同角度出主意，互相激发",
        "default": ["innovator", "pragmatist", "devils_advocate"],
        "roles_per_round": 3,
    },
    "socratic": {
        "description": "AI 通过不断追问帮学生理清思路",
        "default": ["skeptic"],
        "roles_per_round": 1,
    },
    "mock_defense": {
        "description": "模拟答辩/评委提问场景",
        "default": ["skeptic", "devils_advocate", "pragmatist"],
        "roles_per_round": 2,
    },
    "critique": {
        "description": "提交草稿后多个角色从不同角度挑刺",
        "default": ["devils_advocate", "skeptic", "pragmatist", "idealist"],
        "roles_per_round": 2,
    },
    "compare": {
        "description": "逐条对比两种观点，高亮分歧",
        "default": ["pragmatist", "idealist"],
        "roles_per_round": 2,
    },
    "direction_explore": {
        "description": "从零开始探索创新创业方向",
        "default": [],
        "roles_per_round": 0,
    },
    "bp_polish": {
        "description": "商业计划书逐章打磨",
        "default": ["pragmatist", "skeptic", "innovator", "historian"],
        "roles_per_round": 2,
    },
    "roadshow": {
        "description": "路演模拟，投资人/评委连环追问",
        "default": ["skeptic", "devils_advocate", "pragmatist"],
        "roles_per_round": 1,
    },
    "business_model": {
        "description": "多个商业模式假设互相攻防",
        "default": ["pragmatist", "idealist", "skeptic", "innovator"],
        "roles_per_round": 2,
    },
    "risk_explore": {
        "description": "全员找盲区——财务、技术、市场、执行风险",
        "default": ["skeptic", "devils_advocate", "pragmatist", "historian"],
        "roles_per_round": 3,
    },
    "track_compare": {
        "description": "两个方向各派代表辩论，帮你决策",
        "default": ["pragmatist", "idealist", "skeptic", "innovator"],
        "roles_per_round": 2,
    },
    "pain_find": {
        "description": "从方向收窄到具体可解决的问题",
        "default": ["pragmatist", "skeptic", "innovator"],
        "roles_per_round": 3,
    },
    "contest_prep": {
        "description": "比赛答辩模拟，评委角度反复提问",
        "default": ["skeptic", "devils_advocate", "pragmatist", "historian"],
        "roles_per_round": 1,
    },
}


def get_roles_for_mode(mode: str, custom_role_ids: list[str] | None = None) -> list[Role]:
    """获取指定模式的默认角色列表，或自定义角色"""
    if mode == "direction_explore":
        return DIRECTION_ROLES
    role_ids = custom_role_ids or MODE_ROLES.get(mode, {}).get("default", [])
    return [ROLE_LIBRARY[rid] for rid in role_ids if rid in ROLE_LIBRARY]


def list_modes() -> dict:
    """返回所有模式及其说明"""
    return {
        mid: {"description": m["description"], "default_roles": [
            ROLE_LIBRARY[rid].name for rid in m["default"] if rid in ROLE_LIBRARY
        ]}
        for mid, m in MODE_ROLES.items()
    }
