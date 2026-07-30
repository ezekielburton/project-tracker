from app import create_app, db
from app.models import (User, Client, Customer, DeliverableType, DeliverableTypeDiscipline)

app = create_app()

with app.app_context():

    # --- Client ---
    pg = Client.query.filter_by(name='P&G').first()
    if not pg:
        admin = User.query.filter_by(role='admin').first()
        pg = Client(name='P&G', created_by=admin)
        db.session.add(pg)
        db.session.commit()
        print("P&G Client Created")
    else:
        print("P&G Client already exists, skipping")
    
    # --- UAE CUSTOMERS ---
    uae_stores = [
        'Carrefour',
        'Lulu',
        'Union Coop',
        'Nesto',
        'Abu Dhabi Coop',
        'Spinneys',
        'Choithrams',
        'Waitrose'
    ]

    for store in uae_stores:
        existing = Customer.query.filter_by(
            name=store,
            region='uae'
        ).first()
        if not existing:
            customer = Customer(name=store, region='uae')
            db.session.add(customer)
            print(f"Created UAE Customer: {store}")
        else:
            print(f"UAE Customer '{store}' already exists, skipping")
    
    db.session.commit()

    # --- GULF CUSTOMERS ---
    gulf_stores = {
        'kuwait': ['City Center Kuwait', 'Grand Hyper Kuwait', 'Lulu Kuwait', 'Tsc Kuwait'],
        'qatar': ['Carrefour Qatar', 'Lulu Qatar', 'Al Meera Qatar'],
        'bahrain': ['Hyper Max Bahrain', 'Lulu Bahrain'],
        'oman': ['Hypermax Oman', 'Lulu Oman', 'Nesto']
    }

    for region, stores in gulf_stores.items():
        for store in stores:
            existing = Customer.query.filter_by(
                name=store,
                region=region
            ).first()
            if not existing:
                customer = Customer(name=store, region=region)
                db.session.add(customer)
                print(f"Created {region} Customer: {store}")
            else:
                print(f"{region} Customer '{store}' already exists, skipping")

    db.session.commit()

    # --- DELIVERABLE TYPES ---
    deliverable_data = {
        'Carrefour': [
            {

                'name': '1x1 Super Premium',
                'disciplines': ['2d', '3d', 'technical']

            },
            {
                'name': '1x1 Standard Stand',
                'disciplines': ['2d']
            }
        ],
        'Lulu': [
            {
                'name': '1x1 Super Premium',
                'disciplines': ['2d', '3d', 'technical']
            },
            {
                'name': '1x1 Standard Stand',
                'disciplines': ['2d']
            },
            {
                'name': '1x1 Pallet Wrap',
                'disciplines': ['2d']
            }
        ],
    }

    for store_name, deliverables in deliverable_data.items():
     customer = Customer.query.filter_by(
        name=store_name, region='uae'
     ).first()
     if not customer:
        print(f"Customer '{store_name}' not found, skipping deliverables")
        continue

     for item in deliverables:
        existing = DeliverableType.query.filter_by(
            name=item['name'],
            client_id=pg.id,
            customer_id=customer.id
        ).first()
        if not existing:
            dt = DeliverableType(
                name=item['name'],
                client_id=pg.id,
                customer_id=customer.id
            )
            db.session.add(dt)
            db.session.flush()

            for team in item['disciplines']:
               discipline = DeliverableTypeDiscipline(
                    deliverable_type_id=dt.id,
                    team=team
                )
               
            db.session.add(discipline)
               
            print(f"Created Deliverable Type '{item['name']}' for {store_name}")
        else:
            print(f"Deliverable Thype {item['name']} for {store_name} already exists, skipping")

    db.session.commit()
print("Seed Complete")
    