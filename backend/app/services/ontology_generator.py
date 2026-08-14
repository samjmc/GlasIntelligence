"""
Ontology generation service
API 1: Analyze text content and generate entity and relationship type definitions for social simulation

`OntologyGenerator.generate` is the main pipeline entry used by the app (e.g. graph/ontology routes).

`generate_python_code` is optional tooling to emit Python/Zep-style class strings; it is not invoked
by the main request pipeline—only call it from scripts or future tooling if needed.
"""

from typing import Any
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger("glas.ontology_generator")


# The 6 base entity types that are always included in every ontology.
# The LLM adds up to 4 scenario-specific types on top of these.
BASE_ENTITY_TYPES = [
    {
        "name": "PoliticalLeader",
        "description": "Heads of state, ministers, diplomats, elected officials, party leaders",
        "attributes": [
            {"name": "full_name", "type": "text", "description": "Full name of the leader"},
            {"name": "title", "type": "text", "description": "Official title or position"},
        ],
    },
    {
        "name": "MilitaryOrSecurity",
        "description": "Military commanders, intelligence chiefs, police, paramilitary leaders",
        "attributes": [
            {"name": "full_name", "type": "text", "description": "Full name"},
            {"name": "rank_or_role", "type": "text", "description": "Military rank or security role"},
        ],
    },
    {
        "name": "BusinessLeader",
        "description": "CEOs, executives, investors, fund managers, entrepreneurs",
        "attributes": [
            {"name": "full_name", "type": "text", "description": "Full name"},
            {"name": "position", "type": "text", "description": "Corporate title or investment role"},
        ],
    },
    {
        "name": "MediaOrJournalist",
        "description": "Media outlets, journalists, commentators, influencers, bloggers",
        "attributes": [
            {"name": "full_name", "type": "text", "description": "Name of person or outlet"},
            {"name": "media_role", "type": "text", "description": "Journalist, anchor, editor, outlet, etc."},
        ],
    },
    {
        "name": "Person",
        "description": "Any individual not fitting the above specific person types",
        "attributes": [
            {"name": "full_name", "type": "text", "description": "Full name of the person"},
            {"name": "role", "type": "text", "description": "Role or occupation"},
        ],
    },
    {
        "name": "Organization",
        "description": "Any institution, company, government body, NGO, agency, or group",
        "attributes": [
            {"name": "org_name", "type": "text", "description": "Name of the organization"},
            {"name": "org_type", "type": "text", "description": "Type of organization"},
        ],
    },
]

BASE_ENTITY_TYPE_NAMES = {t["name"] for t in BASE_ENTITY_TYPES}

# System prompt for ontology generation
ONTOLOGY_SYSTEM_PROMPT = """You are a professional knowledge graph ontology design expert. Your task is to analyze the given text content and simulation requirements, and design entity types and relationship types suitable for **social media opinion simulation**.

**Important: You must output valid JSON format data, and nothing else.**

## Core Task Background

We are building a **social media opinion simulation system**. In this system:
- Each entity is an "account" or "agent" that can post, interact, and spread information on social media
- Entities influence each other, repost, comment, and respond
- We need to simulate reactions and information propagation paths of various parties in public opinion events

Therefore, **entities must be real-world subjects that can post and interact on social media**:

**Acceptable**:
- Specific individuals (public figures, parties involved, opinion leaders, experts/scholars, ordinary people)
- Companies and enterprises (including their official accounts)
- Organizations and institutions (universities, associations, NGOs, unions, etc.)
- Government departments and regulatory agencies
- Media organizations (newspapers, TV stations, self-media, websites)
- Representatives of specific groups (e.g., alumni associations, fan groups, advocacy groups, etc.)

**Not acceptable**:
- Abstract concepts (e.g., "public opinion", "sentiment", "trend")
- Topics/themes (e.g., "academic integrity", "education reform")
- Viewpoints/attitudes (e.g., "supporters", "opponents")

## Output Format

Please output JSON format with the following structure:

```json
{
    "entity_types": [
        {
            "name": "Entity type name (English, PascalCase)",
            "description": "Brief description (English, max 100 characters)",
            "attributes": [
                {
                    "name": "Attribute name (English, snake_case)",
                    "type": "text",
                    "description": "Attribute description"
                }
            ],
            "examples": ["Example entity 1", "Example entity 2"]
        }
    ],
    "edge_types": [
        {
            "name": "Relationship type name (English, UPPER_SNAKE_CASE)",
            "description": "Brief description (English, max 100 characters)",
            "source_targets": [
                {"source": "Source entity type", "target": "Target entity type"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "Brief analysis summary of the text content"
}
```

## Design Guidelines (Extremely Important!)

### 1. Entity Type Design - HYBRID BASE + DYNAMIC SCHEME

**Total: Exactly 10 entity types.**

**6 BASE TYPES (locked — you MUST include these exactly as specified):**

1. `PoliticalLeader` — Heads of state, ministers, diplomats, elected officials, party leaders
2. `MilitaryOrSecurity` — Military commanders, intelligence chiefs, police, paramilitary leaders
3. `BusinessLeader` — CEOs, executives, investors, fund managers, entrepreneurs
4. `MediaOrJournalist` — Media outlets, journalists, commentators, influencers, bloggers
5. `Person` — Fallback for any individual not matching the 4 specific individual types above
6. `Organization` — Fallback for any institution, company, government body, NGO, agency, or group

These 6 base types MUST appear first in your output, in the order above, with the exact names shown. You may add examples and refine their attributes, but do NOT rename them or omit any.

**4 DYNAMIC TYPES (you design these based on the text and entity inventory):**

After the 6 base types, add exactly 4 additional entity types that capture clusters of entities from the inventory that do NOT fit neatly into the 6 base types.

Rules for dynamic types:
- They must represent real-world actors or groups that can post/interact on social media
- They should cover the LARGEST uncovered entity clusters in the inventory
- Prefer granular actor types over broad categories
- Do NOT duplicate or heavily overlap with the 6 base types
- Good examples: `MilitantGroup`, `ReligiousLeader`, `InternationalOrganization`, `AcademicResearcher`, `LaborUnion`, `RegulatoryAgency`, `CommunityGroup`, `LegalExpert`
- Bad examples: `Government` (overlaps Organization), `PublicFigure` (overlaps Person), `NewsMedia` (overlaps MediaOrJournalist)

### 2. Relationship Type Design

- Quantity: 6-10
- Relationships should reflect real connections in social media interactions
- Ensure the source_targets of relationships cover the entity types you define

### 3. Attribute Design

- 1-3 key attributes per entity type
- **Note**: Attribute names cannot use `name`, `uuid`, `group_id`, `created_at`, `summary` (these are system reserved words)
- Recommended: `full_name`, `title`, `role`, `position`, `location`, `description`, etc.

## Relationship Type Reference

- WORKS_FOR: Works for
- AFFILIATED_WITH: Affiliated with
- REPRESENTS: Represents
- REGULATES: Regulates
- REPORTS_ON: Reports on
- COMMENTS_ON: Comments on
- RESPONDS_TO: Responds to
- SUPPORTS: Supports
- OPPOSES: Opposes
- COLLABORATES_WITH: Collaborates with
- COMPETES_WITH: Competes with
- COMMANDS: Commands or has authority over
"""


class OntologyGenerator:
    """
    Ontology generator
    Analyzes text content and generates entity and relationship type definitions
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client or LLMClient()

    def generate(
        self, document_texts: list[str], simulation_requirement: str, additional_context: str | None = None
    ) -> dict[str, Any]:
        """
        Generate ontology definition with entity inventory pre-scan.

        Args:
            document_texts: List of document texts
            simulation_requirement: Simulation requirement description
            additional_context: Additional context

        Returns:
            Ontology definition (entity_types, edge_types, entity_inventory, etc.)
        """
        combined_text = "\n\n---\n\n".join(document_texts)
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[: self.MAX_TEXT_LENGTH_FOR_LLM]

        entity_inventory = self._extract_entity_inventory(combined_text, simulation_requirement)
        logger.info(f"Entity inventory extracted: {len(entity_inventory)} entities found")

        user_message = self._build_user_message(
            document_texts,
            simulation_requirement,
            additional_context,
            entity_inventory=entity_inventory,
        )

        messages = [{"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT}, {"role": "user", "content": user_message}]

        # Output cap was 4096 tokens: a rich dossier (the full research
        # dossier the frontend uploads) pushes the ontology JSON past it,
        # truncating mid-JSON and failing every retry (V8 verification,
        # 2026-08-14). 16384 comfortably fits a 10-20 entity ontology.
        result = self.llm_client.chat_json(messages=messages, temperature=0.3, max_tokens=16384)

        result = self._validate_and_process(result)
        result["entity_inventory"] = entity_inventory

        return result

    def _extract_entity_inventory(
        self,
        text: str,
        simulation_requirement: str,
    ) -> list[dict[str, Any]]:
        """
        Pre-scan text to build a comprehensive inventory of all concrete entities.

        Returns:
            List of dicts: [{"name": "Shell", "category": "company", "context": "..."}]
        """
        system_prompt = (
            "You are an entity extraction specialist. Your task is to identify EVERY concrete, "
            "real-world entity mentioned in the provided text that could act as a social media "
            "agent (post, comment, interact) or be a meaningful stakeholder in the scenario.\n\n"
            "Include:\n"
            "- Named individuals (politicians, executives, experts, activists, community leaders, academics)\n"
            "- Companies, corporations, and subsidiaries\n"
            "- Government departments, agencies, and local authorities\n"
            "- Regulatory bodies and oversight committees\n"
            "- NGOs, advocacy groups, unions, industry bodies, professional associations\n"
            "- Media outlets and journalists\n"
            "- International organizations\n"
            "- Named community groups, coalitions, or citizen groups\n"
            "- Specific projects, programs, or initiatives that have an organizational identity\n"
            "- Research institutions, universities, and think tanks\n"
            "- Affected communities, neighborhoods, or demographic groups with a distinct identity\n"
            "- Suppliers, contractors, and service providers mentioned by name\n\n"
            "IMPORTANT — also extract entities that are IMPLIED but not explicitly named. For example:\n"
            "- If the text mentions 'the CEO of Acme Corp' without naming them, include 'CEO of Acme Corp' as an individual\n"
            "- If a regulatory approval is discussed, include the relevant regulatory agency even if only alluded to\n"
            "- If community opposition is mentioned, include a representative community group entity\n\n"
            "Do NOT include:\n"
            "- Abstract concepts, topics, or themes\n"
            "- Generic unnamed groups ('some people', 'critics') unless they represent a coherent stakeholder group\n"
            "- Policies or laws unless they have an organizational body behind them\n\n"
            "Aim for AT LEAST 15-30 entities. A richer entity set produces a better simulation. "
            "It is better to include a borderline entity than to miss one.\n\n"
            "Return JSON:\n"
            '{"entities": [\n'
            '  {"name": "Entity name", "category": "individual|company|government|regulator|ngo|media|international_org|industry_body|research|community|other", '
            '"context": "One sentence explaining who/what this entity is and their stake in the scenario"}\n'
            "]}"
        )

        user_prompt = f"Simulation requirement: {simulation_requirement}\n\nDocument text:\n{text[:40000]}"

        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=8192,
            )
            entities = result.get("entities") or []
            seen = set()
            deduped = []
            for e in entities:
                if not isinstance(e, dict):
                    continue
                key = e.get("name", "").strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    deduped.append(e)
            return deduped
        except Exception as e:
            logger.warning(f"Entity inventory extraction failed, continuing without it: {e}")
            return []

    # Max text length sent to LLM (50,000 characters)
    MAX_TEXT_LENGTH_FOR_LLM = 50000

    def _build_user_message(
        self,
        document_texts: list[str],
        simulation_requirement: str,
        additional_context: str | None,
        entity_inventory: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build user message, optionally enriched with entity inventory."""

        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)

        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[: self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(Original text: {original_length} chars, truncated to first {self.MAX_TEXT_LENGTH_FOR_LLM} chars for ontology analysis)..."

        message = f"""## Simulation Requirement

{simulation_requirement}

## Document Content

{combined_text}
"""

        if additional_context:
            message += f"""
## Additional Notes

{additional_context}
"""

        if entity_inventory:
            inventory_lines = []
            for e in entity_inventory:
                inventory_lines.append(f"- {e.get('name', '?')} ({e.get('category', '?')}): {e.get('context', '')}")
            inventory_text = "\n".join(inventory_lines)
            message += f"""
## Entity Inventory (pre-scanned from document)

The following {len(entity_inventory)} concrete entities were identified in the document. Your entity types MUST be designed so that EVERY entity below can be classified into one of your 10 types.

{inventory_text}

**Use these actual entities as `examples` in your entity type definitions — do NOT use generic examples.**
**Your 4 DYNAMIC types should target the biggest uncovered clusters in this inventory** — entities that don't fit neatly into PoliticalLeader, MilitaryOrSecurity, BusinessLeader, MediaOrJournalist, Person, or Organization.
"""

        message += """
Based on the above content, design entity types and relationship types suitable for social opinion simulation.

**Rules that must be followed**:
1. Must output exactly 10 entity types
2. The FIRST 6 must be the locked base types in this exact order: PoliticalLeader, MilitaryOrSecurity, BusinessLeader, MediaOrJournalist, Person, Organization
3. The LAST 4 are dynamic types YOU design based on the text content and entity inventory
4. All entity types must be real-world subjects that can post and interact, not abstract concepts
5. Attribute names cannot use name, uuid, group_id and other reserved words; use full_name, org_name, etc. instead
6. The `examples` field for each entity type must use real entity names from the Entity Inventory above
"""

        return message

    def _validate_and_process(self, result: Any) -> dict[str, Any]:
        """Validate and post-process results.

        Enforces the hybrid 6-base + 4-dynamic entity type scheme:
        - All 6 BASE_ENTITY_TYPES are guaranteed present (injected if LLM omitted any)
        - LLM-provided dynamic types are kept up to 4 slots
        - Total is clamped to exactly 10 entity types
        """
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10
        MAX_DYNAMIC_TYPES = MAX_ENTITY_TYPES - len(BASE_ENTITY_TYPES)  # 4

        if not isinstance(result, dict):
            logger.error(f"Ontology LLM returned non-dict root: {type(result)}. Returning empty ontology.")
            return {"entity_types": [], "edge_types": [], "analysis_summary": ""}

        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""

        RESERVED = {"name", "uuid", "id", "type", "label"}
        for entity in result["entity_types"]:
            if not isinstance(entity, dict):
                continue
            entity["description"] = str(entity.get("description", ""))[:200]
            attrs = entity.get("attributes", [])
            entity["attributes"] = [a for a in attrs if isinstance(a, dict) and a.get("name") not in RESERVED]
            if "examples" not in entity:
                entity["examples"] = []

        for edge in result["edge_types"]:
            if not isinstance(edge, dict):
                continue
            edge["description"] = str(edge.get("description", ""))[:200]
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []

        # Separate LLM output into base types (may have enriched examples) and dynamic types
        llm_base = {}
        dynamic_types = []
        for et in result["entity_types"]:
            if isinstance(et, dict) and et.get("name") in BASE_ENTITY_TYPE_NAMES:
                llm_base[et["name"]] = et
            elif isinstance(et, dict):
                dynamic_types.append(et)

        # Build final base types: use LLM version if it exists (richer examples), else use defaults
        final_base = []
        for base_def in BASE_ENTITY_TYPES:
            if base_def["name"] in llm_base:
                final_base.append(llm_base[base_def["name"]])
            else:
                logger.warning(f"LLM omitted base type '{base_def['name']}', injecting default")
                final_base.append(dict(base_def))

        # Trim dynamic types to available slots
        if len(dynamic_types) > MAX_DYNAMIC_TYPES:
            logger.info(f"LLM returned {len(dynamic_types)} dynamic types, trimming to {MAX_DYNAMIC_TYPES}")
            dynamic_types = dynamic_types[:MAX_DYNAMIC_TYPES]

        result["entity_types"] = final_base + dynamic_types

        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]

        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]

        logger.info(
            f"Ontology validated: {len(final_base)} base + {len(dynamic_types)} dynamic entity types, "
            f"{len(result['edge_types'])} edge types"
        )

        return result

    def generate_python_code(self, ontology: dict[str, Any]) -> str:
        """
        Convert ontology definition to Python code (similar to ontology.py)

        Args:
            ontology: Ontology definition

        Returns:
            Python code string
        """
        code_lines = [
            '"""',
            "Custom entity type definitions",
            "Auto-generated for social opinion simulation",
            '"""',
            "",
            "from pydantic import Field",
            "from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel",
            "",
            "",
            "# ============== Entity Type Definitions ==============",
            "",
        ]

        # Generate entity types
        for entity in ontology.get("entity_types", []):
            name = entity.get("name")
            if not name:
                logger.warning(f"Entity in generate_python_code missing name: {entity}. Skipping.")
                continue
            desc = entity.get("description", f"A {name} entity.")

            code_lines.append(f"class {name}(EntityModel):")
            code_lines.append(f'    """{desc}"""')

            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr.get("name")
                    if not attr_name:
                        logger.warning(f"Attribute in entity {name} missing name: {attr}. Skipping.")
                        continue
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f"    {attr_name}: EntityText = Field(")
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append("        default=None")
                    code_lines.append("    )")
            else:
                code_lines.append("    pass")

            code_lines.append("")
            code_lines.append("")

        code_lines.append("# ============== Edge Type Definitions ==============")
        code_lines.append("")

        # Generate edge types
        for edge in ontology.get("edge_types", []):
            name = edge.get("name")
            if not name:
                logger.warning(f"Edge in generate_python_code missing name: {edge}. Skipping.")
                continue
            # Convert to PascalCase class name
            class_name = "".join(word.capitalize() for word in name.split("_"))
            desc = edge.get("description", f"A {name} relationship.")

            code_lines.append(f"class {class_name}(EdgeModel):")
            code_lines.append(f'    """{desc}"""')

            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr.get("name")
                    if not attr_name:
                        logger.warning(f"Attribute in edge {name} missing name: {attr}. Skipping.")
                        continue
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f"    {attr_name}: EntityText = Field(")
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append("        default=None")
                    code_lines.append("    )")
            else:
                code_lines.append("    pass")

            code_lines.append("")
            code_lines.append("")

        # Generate type dictionaries
        code_lines.append("# ============== Type Configuration ==============")
        code_lines.append("")
        code_lines.append("ENTITY_TYPES = {")
        for entity in ontology.get("entity_types", []):
            ent_name = entity.get("name")
            if not ent_name:
                continue
            code_lines.append(f'    "{ent_name}": {ent_name},')
        code_lines.append("}")
        code_lines.append("")
        code_lines.append("EDGE_TYPES = {")
        for edge in ontology.get("edge_types", []):
            name = edge.get("name")
            if not name:
                continue
            class_name = "".join(word.capitalize() for word in name.split("_"))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append("}")
        code_lines.append("")

        # Generate edge source_targets mapping
        code_lines.append("EDGE_SOURCE_TARGETS = {")
        for edge in ontology.get("edge_types", []):
            name = edge.get("name")
            if not name:
                continue
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ", ".join(
                    [
                        f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                        for st in source_targets
                    ]
                )
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append("}")

        return "\n".join(code_lines)
