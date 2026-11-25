"""Données fictives : exemplaires de recette (`send_test_emails`) et contrôle de chaque gabarit dans les tests."""

_LEASE = {"name": "Ibrahima Kane", "unit": "M07", "property": "Résidence Mermoz"}
_TICKET = {
    "first_name": "Awa", "unit": "M07", "property": "Résidence Mermoz", "category": "Plomberie", "priority": "Urgent",
    "description": "Fuite importante sous la douche, l'eau passe chez le voisin du dessous.", "url": "https://dahoo.sn/espace/maintenance/1",
}

SAMPLES = {
    "account_welcome": {"first_name": "Awa", "organization": "Agence Teranga", "phone": "+221 77 000 00 01", "url": "https://dahoo.sn/confirmer-email/exemple"},
    "email_confirm": {"first_name": "Awa", "email": "awa@teranga.sn", "url": "https://dahoo.sn/confirmer-email/exemple"},
    "password_reset": {"first_name": "Awa", "minutes": 60, "url": "https://dahoo.sn/nouveau-mot-de-passe?id=exemple&jeton=exemple"},
    "password_temporary": {"first_name": "Awa", "author": "Moussa Fall"},
    "password_changed": {"first_name": "Awa", "when": "25/11/2026 à 14:32"},
    "daily_digest": {
        "first_name": "Awa", "organization": "Agence Teranga", "date": "25 novembre 2026", "url": "https://dahoo.sn/espace",
        "sections": [
            {"title": "Loyers en retard : 2 080 000 F CFA", "url": "https://dahoo.sn/espace/loyers", "more": 2, "rows": [
                {"label": "Ibrahima Kane, M07", "value": "1 650 000 F CFA"}, {"label": "Ousmane Faye, M05", "value": "220 000 F CFA"}]},
            {"title": "Encaissé hier : 480 000 F CFA", "url": "https://dahoo.sn/espace/paiements", "more": 0, "rows": [
                {"label": "Mamadou Diallo, Wave", "value": "480 000 F CFA"}]},
            {"title": "Pannes à traiter", "url": "https://dahoo.sn/espace/maintenance", "more": 0, "rows": [
                {"label": "Plomberie, M07", "value": "Urgent"}]},
        ],
    },
    "ticket_created": _TICKET,
    "ticket_assigned": {**_TICKET, "author": "Moussa Fall"},
    "trial_ending": {"first_name": "Awa", "organization": "Agence Teranga", "date": "2 décembre 2026", "url": "https://dahoo.sn/espace/agence"},
    "subscription_receipt": {
        "first_name": "Awa", "organization": "Agence Teranga", "plan": "Basique", "amount": "15 000 F CFA", "method": "Wave",
        "until": "24 décembre 2026", "url": "https://dahoo.sn/d/exemple",
    },
    "subscription_ending": {
        "first_name": "Awa", "organization": "Agence Teranga", "plan": "Basique", "price": "15 000 F CFA", "date": "2 décembre 2026",
        "instructions": "Wave ou Orange Money, en indiquant le nom de l'agence.", "url": "https://dahoo.sn/espace/agence",
    },
    "subscription_ended": {
        "first_name": "Awa", "organization": "Agence Teranga", "date": "2 décembre 2026",
        "instructions": "Wave ou Orange Money, en indiquant le nom de l'agence.", "url": "https://dahoo.sn/espace/agence",
    },
    "plan_request": {
        "first_name": "Mohamed", "organization": "Keur Immo", "plan": "Basique", "contact": "Fatou Sow", "phone": "+221 77 123 45 67",
        "message": "Nous avons 35 lots.", "url": "https://dahoo.sn/plateforme/abonnements",
    },
    "demo_request": {
        "first_name": "Mohamed", "agency": "Keur Immo", "contact": "Fatou Sow", "phone": "+221 77 123 45 67", "email": "fatou@keurimmo.sn",
        "city": "Thiès", "units": "21-100", "message": "Nous suivons les loyers sur Excel.", "url": "https://dahoo.sn/plateforme/demandes",
    },
    "demo_received": {"name": "Fatou Sow", "phone": "+221 77 123 45 67"},
    "rent_receipt": {**_LEASE, "period": "novembre 2026", "amount": "550 000 F CFA", "url": "https://dahoo.sn/d/exemple"},
    "payment_receipt": {"name": "Ibrahima Kane", "amount": "300 000 F CFA", "method": "Wave", "date": "25 novembre 2026", "reference": "T-8841", "url": "https://dahoo.sn/d/exemple"},
    "rent_due": {**_LEASE, "amount": "550 000 F CFA", "date": "5 décembre 2026"},
    "rent_overdue": {**_LEASE, "amount": "1 100 000 F CFA", "count": 2, "since": "5 octobre 2026"},
    "deposit_settlement": {**_LEASE, "held": "900 000 F CFA", "retained": "120 000 F CFA", "refund": "780 000 F CFA", "url": "https://dahoo.sn/d/exemple"},
    "owner_statement": {"name": "Seynabou Diagne", "month": "novembre 2026", "collected": "1 977 000 F CFA", "commission": "197 700 F CFA",
                        "expenses": "45 000 F CFA", "balance": "1 734 300 F CFA", "url": "https://dahoo.sn/d/exemple"},
    "owner_payout": {"name": "Seynabou Diagne", "amount": "1 734 300 F CFA", "date": "8 décembre 2026", "channel": "Virement", "reference": "VIR-2231"},
}
