/** The family of Copilot reporting solutions, rendered by the About page suite block.
 *  Keep this list identical across every sibling repo — when a new solution ships,
 *  add it here and drop its thumbnail into `public/suite/<id>.png` in all repos. */
export interface SuiteSolution {
  id: string;
  name: string;
  eyebrow: string;
  description: string;
  repo: string;
}

/** Identifies which entry is the solution you're currently looking at. */
export const CURRENT_SOLUTION_ID = "usage-reporter";

export const SUITE: SuiteSolution[] = [
  {
    id: "usage-reporter",
    name: "Usage Reporter",
    eyebrow: "M365 Copilot",
    description:
      "Adoption and usage reporting across Microsoft 365 Copilot — leaderboards, laggards, licences and coaching pairs.",
    repo: "https://github.com/loryanstrant/M365Copilot-Usage-Reporter",
  },
  {
    id: "prompt-analyser",
    name: "Prompt Analyser",
    eyebrow: "M365 Copilot",
    description:
      "Scores how well people prompt, using Azure OpenAI to rate quality, GCSE levers, sentiment and sensitivity.",
    repo: "https://github.com/loryanstrant/M365Copilot-Prompt-Analyser",
  },
  {
    id: "cowork-reporter",
    name: "Cowork Reporter",
    eyebrow: "M365 Copilot",
    description:
      "Consumption and usage for Copilot Cowork — Azure cost, Copilot credits, adoption and Purview audit in one view.",
    repo: "https://github.com/loryanstrant/M365Copilot-Cowork-Reporter",
  },
  {
    id: "agent-quality-reporter",
    name: "Agent Quality Reporter",
    eyebrow: "Copilot Studio",
    description:
      "Scores your Copilot Studio agents against a weighted catalogue of patterns and practices, with an optional LLM judge.",
    repo: "https://github.com/loryanstrant/AgentQualityReporter",
  },
];
