"""
Travel Alerts agent for surfacing travel-relevant news for any locale.

Given a place (e.g. "Rome, Italy"), this agent runs several targeted web
searches across news sources and official authorities, then filters the
results down to what actually matters to a traveler — logistics, weather,
safety, and planning — and returns a concise briefing.
"""

from agents import Agent, WebSearchTool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from loguru import logger

from app.agents.common_tools import get_current_date
from app.core.settings import config


def create_travel_alerts_agent(model: str = None) -> Agent:
    """
    Create a Travel Alerts agent that surfaces travel-relevant news for a locale.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Travel Alerts agent
    """
    agent_model = model or config.default_model

    travel = Agent(
        name="Travel Alerts",
        handoff_description="Surfaces travel-relevant alerts and local news for any city/country: things a traveler should know for logistics, weather, safety, or planning (transit strikes, airport disruptions, severe weather, protests, official travel advisories, major events/closures). Use for queries like 'travel alerts for Rome' or 'anything I should know before going to Paris?'.",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are the Travel Alerts assistant. Given a locale (a city, region, or country), you
surface what a traveler should be aware of right now and in the near future — and
nothing else.

Process:
1. Call `get_current_date` so you can frame searches for recency (e.g. include the
   current month/year, "this week", "upcoming").
2. Run SEVERAL targeted `web_search` queries — do not rely on a single search. Cover
   both the city and the country, and lean on these source types:
   - Official travel advisories (e.g. US State Dept travel.state.gov, UK FCDO
     gov.uk/foreign-travel-advice) and the destination's own government/municipal alerts.
   - Transit and airport authorities (strikes, disruptions, closures).
   - The national weather service / severe-weather warnings.
   - Reputable local or English-language news outlets.
   Example angles: "<locale> travel advisory", "<locale> transit strike <month year>",
   "<locale> airport disruption", "<city> weather warning", "<locale> protest demonstration",
   "<city> public holiday OR major event <month year>".
3. Synthesize the findings, keeping ONLY items that affect a traveler's logistics,
   weather, safety, or planning. Discard routine politics, sports, business/markets,
   and celebrity/entertainment news unless it directly impacts travel.

Output format (Markdown). Omit any section that has nothing relevant:
- Start with a brief **⚠️ Need to know** with the 1–3 most important items (or note if
  nothing urgent stands out).
- Then sections as applicable: **🚇 Logistics**, **🌦 Weather**, **🛡 Safety**,
  **📅 Planning**. Use short bullets. Include dates where known.

Ground everything in your search results — do not invent alerts. If searches turn up
nothing noteworthy, say the locale looks clear of notable travel alerts right now.
If the user didn't specify a locale, ask which place they mean.

Be concise and to the point. Answer the user's question directly and do not offer to
continue the conversation.
""",
        tools=[get_current_date, WebSearchTool()],
        model=agent_model,
    )

    logger.debug(f"Travel Alerts agent created with model '{agent_model}'")
    return travel
