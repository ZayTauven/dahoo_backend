"""
Catalogue des e-mails : objet, illustration et destinataire. Le corps est dans templates/emails/<code>.html,
tous sur la même base (reprise des gabarits de Yessal Gui, aux couleurs de Dahoo).

`reminder` : message récurrent, qu'une personne peut refuser (lien de désinscription).
`on_behalf` : envoyé pour le compte de l'agence, à son nom et avec son adresse de réponse.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    subject: str
    illustration: str
    label: str
    reminder: bool = False
    on_behalf: bool = False


CATALOG = {
    # Compte
    "account_welcome": Template("Bienvenue sur Dahoo", "coffret", "Votre compte"),
    "email_confirm": Template("Confirmez votre adresse e-mail", "enveloppe-validee", "Votre compte"),
    "password_reset": Template("Choisissez un nouveau mot de passe", "cadran", "Sécurité"),
    "password_temporary": Template("Un mot de passe provisoire vous a été attribué", "porte-voix", "Sécurité"),
    "password_changed": Template("Votre mot de passe a été modifié", "cadran", "Sécurité"),
    # Équipe de l'agence
    "daily_digest": Template("Votre point du jour, {organization}", "presse-papiers", "Point du jour"),
    "ticket_created": Template("Nouvelle panne : {unit}", "cone-signalisation", "Maintenance"),
    "ticket_assigned": Template("Une intervention vous est confiée : {unit}", "cone-signalisation", "Maintenance"),
    "trial_ending": Template("Votre essai se termine le {date}", "reveil-enveloppe", "Abonnement"),
    "subscription_receipt": Template("Votre abonnement est réglé jusqu'au {until}", "enveloppe-validee", "Abonnement"),
    "subscription_ending": Template("Votre abonnement se termine le {date}", "reveil-enveloppe", "Abonnement"),
    "subscription_ended": Template("Votre espace est en lecture seule", "reveil-enveloppe", "Abonnement"),
    # Équipe Dahoo et prospects
    "plan_request": Template("{organization} demande l'offre {plan}", "porte-voix", "Abonnements"),
    "demo_request": Template("Demande de démo : {agency}", "porte-voix", "Demandes"),
    "demo_received": Template("Nous avons bien reçu votre demande", "parachute", "Démonstration"),
    # Locataires, pour le compte de l'agence
    "rent_receipt": Template("Votre quittance de loyer, {period}", "enveloppe-validee", "Quittance", on_behalf=True),
    "payment_receipt": Template("Nous avons bien reçu votre paiement", "enveloppe-validee", "Reçu", on_behalf=True),
    "rent_due": Template("Votre loyer est à régler le {date}", "reveil-enveloppe", "Loyer", reminder=True, on_behalf=True),
    "rent_overdue": Template("Un loyer reste à régler", "presse-papiers", "Loyer", reminder=True, on_behalf=True),
    "deposit_settlement": Template("Le décompte de votre caution", "presse-papiers", "Caution", on_behalf=True),
    # Bailleurs, pour le compte de l'agence
    "owner_statement": Template("Votre relevé de gestion, {month}", "presse-papiers", "Relevé", on_behalf=True),
    "owner_payout": Template("Un reversement vous a été adressé", "gift", "Reversement", on_behalf=True),
}
