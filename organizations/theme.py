"""
Apparence de l'espace agence (personnaliseur) : clés et valeurs autorisées. Tout le reste est refusé,
pour que le front n'applique jamais de valeur arbitraire sur la page. Stockée dans Organization.theme.
"""

from rest_framework import serializers

SCHEMES = [("light", "Clair"), ("dark", "Sombre"), ("brand", "Marque"), ("gradient", "Dégradé"), ("transparent", "Transparent")]
ACCENTS = [
    ("dahoo", "Dahoo"), ("verdigris", "Vert-de-gris"), ("cobalt", "Cobalt"), ("indigo", "Indigo"),
    ("amethyst", "Améthyste"), ("magenta", "Magenta"), ("terracotta", "Terracotta"), ("amber", "Ambre"),
    ("olive", "Olive"), ("forest", "Forêt"), ("teal", "Sarcelle"), ("slate", "Ardoise"), ("graphite", "Graphite"),
    ("custom", "Personnalisée"),
]


class OrganizationThemeSerializer(serializers.Serializer):
    """Réglages facultatifs : une clé absente = valeur par défaut de Dahoo."""

    accent = serializers.ChoiceField(choices=ACCENTS, required=False)
    accent_custom = serializers.RegexField(r"^#[0-9a-fA-F]{6}$", required=False, help_text="#RRGGBB, si accent = custom")
    sidebar = serializers.ChoiceField(choices=SCHEMES, required=False)
    header = serializers.ChoiceField(choices=SCHEMES, required=False)
    shell = serializers.ChoiceField(choices=[("default", "Collé"), ("detached", "Détaché")], required=False)
    sidebar_behavior = serializers.ChoiceField(
        choices=[("collapsible", "Repliable"), ("expanded", "Déplié"), ("compact", "Compact")], required=False
    )
    page = serializers.ChoiceField(choices=[("regular", "Standard"), ("classic", "Classique"), ("compact", "Compact")], required=False)
    width = serializers.ChoiceField(choices=[("fluid", "Centrée"), ("full", "Pleine largeur")], required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: "Réglage inconnu." for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs.get("accent") == "custom" and not attrs.get("accent_custom"):
            raise serializers.ValidationError({"accent_custom": "Choisissez la couleur personnalisée."})
        if "accent_custom" in attrs:
            attrs["accent_custom"] = attrs["accent_custom"].upper()
        return attrs
