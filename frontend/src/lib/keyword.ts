const STOP = new Set(["DE", "DA", "DO", "DOS", "DAS", "LDA", "SA", "WWW", "COM", "PT", "LISBOA", "PORTO", "LOURES"]);

/** Palavra-chave proposta para uma regra (igual à do servidor): 1.º token útil com >= 4 caracteres. */
export function suggestKeyword(descricaoNormalizada: string): string {
  const tokens = descricaoNormalizada.split(/\s+/).map((t) => t.replace(/^\W+|\W+$/g, "")).filter((t) => t && !STOP.has(t));
  return tokens.find((t) => t.length >= 4) ?? tokens.slice(0, 2).join(" ") ?? descricaoNormalizada;
}
