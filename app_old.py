
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import sqlite3
import os
import heapq

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'smartpark.db')

app = Flask(__name__)
app.secret_key = os.environ.get(
    'SMARTPARK_SECRET',
    'change-this-secret-before-deployment'
)


SLOT_ROWS = ['A', 'B', 'C']
SLOTS_PER_ROW = 8

# Available vehicle entrances and the junction each connects to.
ENTRANCES = {
    'ENTRANCE1': {
        'name': 'Entrance 1',
        'description': 'Main vehicle entrance',
        'junction': 'J1',
    },
    'ENTRANCE2': {
        'name': 'Entrance 2',
        'description': 'Secondary vehicle entrance',
        'junction': 'J3',
    },
}



# ---------------- DATABASE ----------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def now_text():
    return datetime.now().replace(microsecond=0).isoformat(sep=' ')


def init_db():
    con = db()

    con.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE COLLATE NOCASE,
        phone TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL UNIQUE,
        row_name TEXT NOT NULL,
        node TEXT NOT NULL UNIQUE,
        size TEXT NOT NULL DEFAULT 'standard',
        accessible INTEGER NOT NULL DEFAULT 0,
        ev_charging INTEGER NOT NULL DEFAULT 0,
        base_status TEXT NOT NULL DEFAULT 'available'
    );

    CREATE TABLE IF NOT EXISTS roads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_a TEXT NOT NULL,
        node_b TEXT NOT NULL,
        distance REAL NOT NULL,
        blocked INTEGER NOT NULL DEFAULT 0,
        UNIQUE(node_a, node_b)
    );

    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        slot_id INTEGER NOT NULL REFERENCES slots(id),
        start_at TEXT NOT NULL,
        end_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'confirmed',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        read INTEGER NOT NULL DEFAULT 0
    );
    ''')

    # Add arrival tracking to an existing database.
    columns = {
        row['name']
        for row in con.execute("PRAGMA table_info(reservations)")
    }

    if 'arrived' not in columns:
        con.execute("""
            ALTER TABLE reservations
            ADD COLUMN arrived INTEGER NOT NULL DEFAULT 0
        """)

    # Create the initial 24 parking spaces.
    if con.execute('SELECT COUNT(*) FROM slots').fetchone()[0] == 0:
        for row_name in SLOT_ROWS:
            for n in range(1, SLOTS_PER_ROW + 1):
                label = f'{row_name}{n}'

                size = (
                    'compact' if n in (1, 8)
                    else 'large' if n in (4, 5)
                    else 'standard'
                )

                con.execute("""
                    INSERT INTO slots
                    (label, row_name, node, size, accessible, ev_charging)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    label, row_name, label, size,
                    int(n == 1), int(n == 4)
                ))

        edges = [
            ('ENTRANCE', 'J1', 2),
            ('ENTRANCE', 'J2', 7),
            ('J1', 'J2', 4),
            ('J2', 'J3', 4),
            ('J1', 'J3', 9)
        ]

        for i in range(1, 9):
            edges.append(('J1', f'A{i}', 1 + (i % 3)))
            edges.append(('J2', f'B{i}', 1 + (i % 3)))
            edges.append(('J3', f'C{i}', 1 + (i % 3)))

        for a, b, distance in edges:
            con.execute("""
                INSERT INTO roads (node_a, node_b, distance)
                VALUES (?, ?, ?)
            """, (a, b, distance))

    # Create a default administrator if none exists.
    if not con.execute(
        "SELECT id FROM users WHERE role='admin' LIMIT 1"
    ).fetchone():
        con.execute("""
            INSERT INTO users
            (name, email, phone, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'SmartPark Admin',
            'admin@smartpark.local',
            None,
            generate_password_hash('Admin123!'),
            'admin',
            now_text()
        ))

    con.commit()
    con.close()


# ---------------- AUTHENTICATION ----------------

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to continue.', 'info')
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))

        if session.get('role') != 'admin':
            abort(403)

        return fn(*args, **kwargs)
    return wrapped


def current_user():
    if not session.get('user_id'):
        return None

    con = db()
    user = con.execute("""
        SELECT id, name, email, phone, role
        FROM users WHERE id = ?
    """, (session['user_id'],)).fetchone()
    con.close()

    return user


# ---------------- GRAPH THEORY / ROUTING ----------------

def get_graph(con):
    graph = {}

    for road in con.execute(
        'SELECT node_a, node_b, distance FROM roads WHERE blocked = 0'
    ):
        graph.setdefault(road['node_a'], []).append(
            (road['node_b'], float(road['distance']))
        )
        graph.setdefault(road['node_b'], []).append(
            (road['node_a'], float(road['distance']))
        )

    return graph


def dijkstra(graph, start, target):
    queue = [(0.0, start)]
    distances = {start: 0.0}
    previous = {}

    while queue:
        distance, node = heapq.heappop(queue)

        if distance != distances.get(node):
            continue

        if node == target:
            break

        for neighbor, weight in graph.get(node, []):
            candidate = distance + weight

            if candidate < distances.get(neighbor, float('inf')):
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))

    if target not in distances:
        return None, None

    path = []
    node = target

    while node != start:
        path.append(node)
        node = previous[node]

    path.append(start)
    path.reverse()

    return path, distances[target]


# ---------------- PARKING STATUS ----------------

def slot_status(con, slot):
    if slot['base_status'] == 'occupied':
        return 'occupied'

    now = now_text()

    reservation = con.execute("""
        SELECT arrived
        FROM reservations
        WHERE slot_id = ?
          AND status = 'confirmed'
          AND end_at > ?
        ORDER BY start_at ASC
        LIMIT 1
    """, (slot['id'], now)).fetchone()

    if reservation and reservation['arrived']:
        return 'occupied'

    if reservation:
        return 'reserved'

    return 'available'


def all_slots(con):
    result = []

    rows = con.execute("""
        SELECT * FROM slots
        ORDER BY row_name, CAST(substr(label, 2) AS INTEGER)
    """)

    for slot in rows:
        item = dict(slot)
        item['status'] = slot_status(con, slot)
        result.append(item)

    return result


def stats(con):
    slots = all_slots(con)
    total = len(slots)

    occupied = sum(s['status'] == 'occupied' for s in slots)
    reserved = sum(s['status'] == 'reserved' for s in slots)
    available = sum(s['status'] == 'available' for s in slots)

    occupancy = round(occupied * 100 / total) if total else 0

    return {
        'total': total,
        'occupied': occupied,
        'reserved': reserved,
        'available': available,
        'occupancy': occupancy
    }


# ---------------- ALERTS ----------------

def create_alert(con, user_id, message):
    con.execute("""
        INSERT INTO alerts (user_id, message, created_at)
        VALUES (?, ?, ?)
    """, (user_id, message, now_text()))


def refresh_expiry_alerts(con, user_id):
    now = datetime.now().replace(microsecond=0)
    soon = (now + timedelta(minutes=30)).isoformat(sep=' ')
    current = now.isoformat(sep=' ')

    rows = con.execute("""
        SELECT r.id, s.label, r.end_at
        FROM reservations r
        JOIN slots s ON s.id = r.slot_id
        WHERE r.user_id = ?
          AND r.status = 'confirmed'
          AND r.end_at > ?
          AND r.end_at <= ?
    """, (user_id, current, soon)).fetchall()

    for row in rows:
        message = (
            f"Reservation for {row['label']} ends soon "
            f"({row['end_at']})."
        )

        exists = con.execute("""
            SELECT id FROM alerts
            WHERE user_id = ? AND message = ?
        """, (user_id, message)).fetchone()

        if not exists:
            create_alert(con, user_id, message)

    con.commit()


@app.context_processor
def inject_globals():
    return {
        'current_user': current_user(),
        'year': datetime.now().year
    }


# ---------------- HOME ----------------

@app.route('/')
def index():
    con = db()
    data = stats(con)
    con.close()

    return render_template('index.html', stats=data)


# ---------------- REGISTER ----------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower() or None
        phone = request.form.get('phone', '').strip() or None
        password = request.form.get('password', '')

        if not name or not password or (not email and not phone):
            flash(
                'Enter your name, password, and at least an email '
                'address or phone number.',
                'error'
            )

        elif len(password) < 8:
            flash('Use a password with at least 8 characters.', 'error')

        else:
            con = db()

            try:
                cur = con.execute("""
                    INSERT INTO users
                    (name, email, phone, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    name, email, phone,
                    generate_password_hash(password), now_text()
                ))

                con.commit()
                session.update(
                    user_id=cur.lastrowid,
                    name=name,
                    role='user'
                )

                flash('Your account is ready. Welcome to SmartPark!', 'success')
                return redirect(url_for('dashboard'))

            except sqlite3.IntegrityError:
                flash(
                    'That email address or phone number is already registered.',
                    'error'
                )

            finally:
                con.close()

    return render_template('register.html')


# ---------------- LOGIN / LOGOUT ----------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '')

        con = db()
        user = con.execute("""
            SELECT * FROM users
            WHERE lower(email) = lower(?) OR phone = ?
        """, (identifier, identifier)).fetchone()
        con.close()

        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session.update(
                user_id=user['id'],
                name=user['name'],
                role=user['role']
            )

            flash('You are now logged in.', 'success')

            if user['role'] == 'admin':
                return redirect(url_for('admin'))

            return redirect(url_for('dashboard'))

        flash('The email/phone or password is incorrect.', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ---------------- USER DASHBOARD ----------------

@app.route('/dashboard')
@login_required
def dashboard():
    con = db()

    refresh_expiry_alerts(con, session['user_id'])
    data = stats(con)
    slots = all_slots(con)

    reservations = con.execute("""
        SELECT r.*, s.label
        FROM reservations r
        JOIN slots s ON s.id = r.slot_id
        WHERE r.user_id = ?
        ORDER BY r.start_at DESC
        LIMIT 5
    """, (session['user_id'],)).fetchall()

    alerts = con.execute("""
        SELECT * FROM alerts
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (session['user_id'],)).fetchall()

    con.close()

    return render_template(
        'dashboard.html',
        stats=data,
        slots=slots,
        reservations=reservations,
        alerts=alerts
    )


# ---------------- BOOK A PARKING SPACE ----------------

@app.route('/book', methods=['GET', 'POST'])
@login_required
def book():
    con = db()

    if request.method == 'POST':
        try:
            start = datetime.fromisoformat(
                request.form['start_at']
            ).replace(second=0, microsecond=0)

            end = datetime.fromisoformat(
                request.form['end_at']
            ).replace(second=0, microsecond=0)

        except (ValueError, KeyError):
            con.close()
            flash('Please choose a valid start and end time.', 'error')
            return redirect(url_for('book'))

        now = datetime.now().replace(second=0, microsecond=0)

        if start < now or end <= start:
            con.close()
            flash(
                'Choose a future start time and an end time after the start.',
                'error'
            )
            return redirect(url_for('book'))

        vehicle = request.form.get('vehicle_type', 'car')
        accessible = request.form.get('accessible') == 'yes'
        ev = request.form.get('ev') == 'yes'
        assignment_mode = request.form.get('assignment_mode', 'automatic')

        graph = get_graph(con)
        candidates = []

        for slot in con.execute(
            'SELECT * FROM slots WHERE base_status = "available"'
        ):
            if accessible and not slot['accessible']:
                continue

            if ev and not slot['ev_charging']:
                continue

            if vehicle == 'suv' and slot['size'] == 'compact':
                continue

            conflict = con.execute("""
                SELECT id FROM reservations
                WHERE slot_id = ?
                  AND status = 'confirmed'
                  AND start_at < ?
                  AND end_at > ?
                LIMIT 1
            """, (
                slot['id'],
                end.isoformat(sep=' '),
                start.isoformat(sep=' ')
            )).fetchone()

            if conflict:
                continue

            path, distance = dijkstra(
                graph, 'ENTRANCE', slot['node']
            )

            if path is None:
                continue

            candidates.append((distance, slot, path))

        if not candidates:
            con.close()
            flash(
                'No suitable spaces are available for those requirements '
                'and times. Try different times or requirements.',
                'error'
            )
            return redirect(url_for('book'))

        candidates.sort(key=lambda x: (x[0], x[1]['label']))

        if assignment_mode == 'manual':
            selected_id = request.form.get('slot_id', '')

            chosen = next(
                (
                    item for item in candidates
                    if str(item[1]['id']) == selected_id
                ),
                None
            )

            if not chosen:
                con.close()
                flash(
                    'That slot is not available for your selected time '
                    'and requirements. Choose another space or use '
                    'automatic assignment.',
                    'error'
                )
                return redirect(url_for('book'))

            distance, slot, path = chosen

        else:
            distance, slot, path = candidates[0]

        try:
            cur = con.execute("""
                INSERT INTO reservations
                (user_id, slot_id, start_at, end_at, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session['user_id'],
                slot['id'],
                start.isoformat(sep=' '),
                end.isoformat(sep=' '),
                'confirmed',
                now_text()
            ))

            create_alert(
                con,
                session['user_id'],
                f"Booking confirmed: slot {slot['label']} from "
                f"{start.strftime('%d %b, %H:%M')} to "
                f"{end.strftime('%H:%M')}."
            )

            con.commit()
            reservation_id = cur.lastrowid

        except sqlite3.IntegrityError:
            con.rollback()
            con.close()
            flash('That space was just booked. Please try again.', 'error')
            return redirect(url_for('book'))

        con.close()

        return redirect(
            url_for('route_view', reservation_id=reservation_id)
        )

    default_start = (
        datetime.now() + timedelta(hours=1)
    ).replace(minute=0, second=0, microsecond=0)

    default_end = default_start + timedelta(hours=2)

    slots = all_slots(con)
    con.close()

    return render_template(
        'book.html',
        slots=slots,
        default_start=default_start.strftime('%Y-%m-%dT%H:%M'),
        default_end=default_end.strftime('%Y-%m-%dT%H:%M')
    )


# ---------------- ROUTE VIEW ----------------

@app.route('/route/<int:reservation_id>')
@login_required
def route_view(reservation_id):
    con = db()

    reservation = con.execute("""
        SELECT r.*, s.label, s.node, s.size
        FROM reservations r
        JOIN slots s ON s.id = r.slot_id
        WHERE r.id = ?
    """, (reservation_id,)).fetchone()

    if (
        not reservation
        or (
            reservation['user_id'] != session['user_id']
            and session.get('role') != 'admin'
        )
    ):
        con.close()
        abort(404)

    path, distance = dijkstra(
        get_graph(con), 'ENTRANCE', reservation['node']
    )

    con.close()

    return render_template(
        'route.html',
        reservation=reservation,
        path=path,
        distance=distance
    )


# ---------------- RESERVATIONS ----------------

@app.route('/reservations')
@login_required
def reservations():
    con = db()

    rows = con.execute("""
        SELECT r.*, s.label
        FROM reservations r
        JOIN slots s ON s.id = r.slot_id
        WHERE r.user_id = ?
        ORDER BY r.start_at DESC
    """, (session['user_id'],)).fetchall()

    con.close()

    return render_template('reservations.html', reservations=rows)


@app.route('/reservations/<int:reservation_id>/cancel', methods=['POST'])
@login_required
def cancel_reservation(reservation_id):
    con = db()

    row = con.execute("""
        SELECT * FROM reservations
        WHERE id = ? AND user_id = ?
    """, (reservation_id, session['user_id'])).fetchone()

    if row and row['status'] == 'confirmed':
        con.execute("""
            UPDATE reservations
            SET status = 'cancelled', arrived = 0
            WHERE id = ?
        """, (reservation_id,))

        create_alert(
            con,
            session['user_id'],
            'Your reservation has been cancelled.'
        )

        con.commit()
        flash('Reservation cancelled.', 'success')

    else:
        flash('Reservation could not be cancelled.', 'error')

    con.close()
    return redirect(url_for('reservations'))


# ---------------- USER ARRIVAL ----------------

@app.route(
    '/reservation/<int:reservation_id>/arrive',
    methods=['POST']
)
@login_required
def mark_arrived(reservation_id):
    con = db()
    now = now_text()

    reservation = con.execute("""
        SELECT r.*, s.label
        FROM reservations r
        JOIN slots s ON s.id = r.slot_id
        WHERE r.id = ?
          AND r.user_id = ?
          AND r.status = 'confirmed'
    """, (reservation_id, session['user_id'])).fetchone()

    if not reservation:
        con.close()
        flash('Reservation not found or no longer active.', 'error')
        return redirect(url_for('dashboard'))

    if not (reservation['start_at'] <= now < reservation['end_at']):
        con.close()
        flash(
            'You can confirm arrival only during your booking time.',
            'error'
        )
        return redirect(url_for('dashboard'))

    con.execute("""
        UPDATE reservations
        SET arrived = 1
        WHERE id = ?
    """, (reservation_id,))

    create_alert(
        con,
        session['user_id'],
        f"You confirmed arrival at parking spot {reservation['label']}."
    )

    con.commit()
    con.close()

    flash(
        f"Arrival confirmed! Spot {reservation['label']} is now occupied.",
        'success'
    )

    return redirect(url_for('dashboard'))


# ---------------- USER DEPARTURE ----------------

@app.route(
    '/reservation/<int:reservation_id>/leave',
    methods=['POST']
)
@login_required
def mark_left(reservation_id):
    con = db()

    reservation = con.execute("""
        SELECT r.*, s.label
        FROM reservations r
        JOIN slots s ON s.id = r.slot_id
        WHERE r.id = ?
          AND r.user_id = ?
          AND r.status = 'confirmed'
    """, (reservation_id, session['user_id'])).fetchone()

    if not reservation or not reservation['arrived']:
        con.close()
        flash('No active arrival was found for this reservation.', 'error')
        return redirect(url_for('dashboard'))

    con.execute("""
        UPDATE reservations
        SET status = 'completed', arrived = 0
        WHERE id = ?
    """, (reservation_id,))

    create_alert(
        con,
        session['user_id'],
        f"You confirmed departure from parking spot {reservation['label']}."
    )

    con.commit()
    con.close()

    flash(
        'Departure confirmed. Your parking spot has been released.',
        'success'
    )

    return redirect(url_for('dashboard'))


# ---------------- ADMIN ----------------

@app.route('/admin')
@admin_required
def admin():
    con = db()

    data = stats(con)
    roads = con.execute('SELECT * FROM roads ORDER BY id').fetchall()

    slots = all_slots(con)

    recent = con.execute("""
        SELECT r.*, s.label, u.name
        FROM reservations r
        JOIN slots s ON s.id = r.slot_id
        JOIN users u ON u.id = r.user_id
        ORDER BY r.created_at DESC
        LIMIT 10
    """).fetchall()

    con.close()

    return render_template(
        'admin.html',
        stats=data,
        roads=roads,
        slots=slots,
        reservations=recent
    )


@app.route('/admin/road/<int:road_id>/toggle', methods=['POST'])
@admin_required
def toggle_road(road_id):
    con = db()

    road = con.execute(
        'SELECT * FROM roads WHERE id = ?', (road_id,)
    ).fetchone()

    if not road:
        con.close()
        abort(404)

    blocked = 0 if road['blocked'] else 1

    con.execute(
        'UPDATE roads SET blocked = ? WHERE id = ?',
        (blocked, road_id)
    )

    con.commit()
    con.close()

    flash(
        'Road marked as blocked.' if blocked
        else 'Road reopened. Routes will use the updated map.',
        'success'
    )

    return redirect(url_for('admin'))


@app.route('/admin/slot/<int:slot_id>/toggle', methods=['POST'])
@admin_required
def toggle_slot(slot_id):
    con = db()

    slot = con.execute(
        'SELECT * FROM slots WHERE id = ?', (slot_id,)
    ).fetchone()

    if not slot:
        con.close()
        abort(404)

    new_status = (
        'available'
        if slot['base_status'] == 'occupied'
        else 'occupied'
    )

    con.execute(
        'UPDATE slots SET base_status = ? WHERE id = ?',
        (new_status, slot_id)
    )

    con.commit()
    con.close()

    flash(f"Slot {slot['label']} marked {new_status}.", 'success')
    return redirect(url_for('admin'))


# ---------------- ALERTS PAGE ----------------

@app.route('/alerts')
@login_required
def alerts():
    con = db()

    refresh_expiry_alerts(con, session['user_id'])

    rows = con.execute("""
        SELECT * FROM alerts
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (session['user_id'],)).fetchall()

    con.execute("""
        UPDATE alerts SET read = 1
        WHERE user_id = ?
    """, (session['user_id'],))

    con.commit()
    con.close()

    return render_template('alerts.html', alerts=rows)


# ---------------- ERROR HANDLING ----------------

@app.errorhandler(403)
def forbidden(_):
    return render_template(
        'message.html',
        title='Access restricted',
        message='This page is only available to administrators.'
    ), 403


# ---------------- RUN APPLICATION ----------------

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
