from flask import Flask
from flask import render_template
from flask import request
from flask import redirect
from flask import url_for
from flask import flash
import db
import connect
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'sds_secret_2025'  # Set a secret key for session/flash

# Initialize database connection
db.init_db(
    app, connect.dbuser, connect.dbpass, connect.dbhost, connect.dbname, connect.dbport
)


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/teachers", methods=["GET"])
def teacher_list():
    cursor = db.get_cursor()
    querystr = "SELECT teacher_id, first_name, last_name FROM teachers;"
    cursor.execute(querystr)
    teachers = cursor.fetchall()
    cursor.close()
    return render_template("teacher_list.html", teachers=teachers)


@app.route("/students", methods=["GET"])
def student_list():
    cursor = db.get_cursor()
    search_term = request.args.get('search')
    if search_term:
        term = '%' + search_term + '%'
        query = """
                SELECT student_id, first_name, last_name, email, phone, date_of_birth, enrollment_date
                FROM students
                WHERE first_name LIKE %s \
                   OR last_name LIKE %s
                ORDER BY last_name, first_name; \
                """
        cursor.execute(query, (term, term))
    else:
        query = """
                SELECT student_id, first_name, last_name, email, phone, date_of_birth, enrollment_date
                FROM students
                ORDER BY student_id, last_name, first_name; \
                """
        cursor.execute(query)
    students = cursor.fetchall()
    # Format dates
    for student in students:
        student['dob_str'] = student['date_of_birth'].strftime('%d/%m/%Y') if student['date_of_birth'] else ''
        student['enroll_str'] = student['enrollment_date'].strftime('%d/%m/%Y') if student['enrollment_date'] else ''
    cursor.close()
    return render_template("student_list.html", students=students, search_term=search_term)


@app.route("/classes")
def class_list():
    cursor = db.get_cursor()
    # Get classes ordered by dance type and grade level
    query_classes = """
                    SELECT c.class_id, \
                           c.class_name, \
                           dt.dancetype_name, \
                           g.grade_name,
                           t.first_name AS teacher_first, \
                           t.last_name  AS teacher_last,
                           c.schedule_day, \
                           c.schedule_time
                    FROM classes c
                             JOIN dancetype dt ON c.dancetype_id = dt.dancetype_id
                             JOIN grades g ON c.grade_id = g.grade_id
                             JOIN teachers t ON c.teacher_id = t.teacher_id
                    ORDER BY dt.dancetype_name, g.grade_level; \
                    """
    cursor.execute(query_classes)
    classes = cursor.fetchall()

    # Get all enrolled students per class
    query_students = """
                     SELECT sc.class_id, s.student_id, s.first_name, s.last_name
                     FROM studentclasses sc
                              JOIN students s ON sc.student_id = s.student_id
                     ORDER BY sc.class_id, s.last_name, s.first_name; \
                     """
    cursor.execute(query_students)
    enrolled = cursor.fetchall()

    # Group students by class in Python
    class_students = {cls['class_id']: [] for cls in classes}
    for enr in enrolled:
        class_students[enr['class_id']].append(enr)

    cursor.close()
    return render_template("class_list.html", classes=classes, class_students=class_students)


@app.route("/student/<int:student_id>")
def student_summary(student_id):
    cursor = db.get_cursor()
    # Get student details
    query_student = "SELECT * FROM students WHERE student_id = %s;"
    cursor.execute(query_student, (student_id,))
    student = cursor.fetchone()
    if not student:
        flash("Student not found", "error")
        return redirect(url_for('student_list'))
    student['dob_str'] = student['date_of_birth'].strftime('%d/%m/%Y') if student['date_of_birth'] else ''
    student['enroll_str'] = student['enrollment_date'].strftime('%d/%m/%Y') if student['enrollment_date'] else ''

    # Get enrolled classes
    query_classes = """
                    SELECT c.class_id, \
                           c.class_name, \
                           dt.dancetype_name, \
                           g.grade_name,
                           t.first_name AS teacher_first, \
                           t.last_name  AS teacher_last,
                           c.schedule_day, \
                           c.schedule_time
                    FROM studentclasses sc
                             JOIN classes c ON sc.class_id = c.class_id
                             JOIN dancetype dt ON c.dancetype_id = dt.dancetype_id
                             JOIN grades g ON c.grade_id = g.grade_id
                             JOIN teachers t ON c.teacher_id = t.teacher_id
                    WHERE sc.student_id = %s
                    ORDER BY dt.dancetype_name, g.grade_level; \
                    """
    cursor.execute(query_classes, (student_id,))
    classes = cursor.fetchall()

    # Get available classes for enrolment
    # Student's current grades per dance type
    student_grades = {}
    query_grades = """
                   SELECT sg.dancetype_id, g.grade_level
                   FROM studentgrades sg
                            JOIN grades g ON sg.grade_id = g.grade_id
                   WHERE sg.student_id = %s; \
                   """
    cursor.execute(query_grades, (student_id,))
    for row in cursor.fetchall():
        student_grades[row['dancetype_id']] = row['grade_level']

    # Potential classes not enrolled
    query_potential = """
                      SELECT c.class_id, c.class_name, dt.dancetype_name, g.grade_name, g.grade_level, dt.dancetype_id
                      FROM classes c
                               JOIN dancetype dt ON c.dancetype_id = dt.dancetype_id
                               JOIN grades g ON c.grade_id = g.grade_id
                      WHERE c.class_id NOT IN (SELECT class_id FROM studentclasses WHERE student_id = %s); \
                      """
    cursor.execute(query_potential, (student_id,))
    all_potential = cursor.fetchall()

    available_classes = []
    for cls in all_potential:
        dt_id = cls['dancetype_id']
        if dt_id in student_grades:
            current_level = student_grades[dt_id]
            class_level = cls['grade_level']
            if class_level == current_level or class_level == current_level + 1:
                available_classes.append(cls)

    cursor.close()
    return render_template("student_summary.html", student=student, classes=classes,
                           available_classes=available_classes)


@app.route("/enrol/<int:student_id>", methods=["POST"])
def enrol(student_id):
    cursor = db.get_cursor()
    class_id = request.form.get('class_id')
    if not class_id:
        flash("No class selected", "error")
        return redirect(url_for('student_summary', student_id=student_id))
    try:
        query = "INSERT INTO studentclasses (student_id, class_id) VALUES (%s, %s);"
        cursor.execute(query, (student_id, class_id))
        db.get_db().commit()
        flash("Enrolled successfully", "success")
    except db.get_db().IntegrityError:
        flash("Already enrolled in this class", "error")
    cursor.close()
    return redirect(url_for('student_summary', student_id=student_id))


@app.route("/add_student", methods=["GET", "POST"])
def add_student():
    if request.method == "POST":
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        dob_str = request.form.get('date_of_birth')
        enroll_str = request.form.get('enrollment_date') or datetime.today().strftime('%Y-%m-%d')

        # Basic validation
        if not first_name or not last_name:
            flash("First and last name are required", "error")
            return render_template("add_student.html", today=datetime.today().strftime('%Y-%m-%d'), form=request.form)

        try:
            dob = datetime.strptime(dob_str, '%Y-%m-%d') if dob_str else None
            enroll = datetime.strptime(enroll_str, '%Y-%m-%d')
            if enroll > datetime.today():
                flash("Enrollment date cannot be in the future", "error")
                return render_template("add_student.html", today=datetime.today().strftime('%Y-%m-%d'),
                                       form=request.form)
        except ValueError:
            flash("Invalid date format", "error")
            return render_template("add_student.html", today=datetime.today().strftime('%Y-%m-%d'), form=request.form)

        cursor = db.get_cursor()
        query = """
                INSERT INTO students (first_name, last_name, email, phone, date_of_birth, enrollment_date)
                VALUES (%s, %s, %s, %s, %s, %s); \
                """
        cursor.execute(query, (first_name, last_name, email, phone, dob, enroll))
        db.get_db().commit()
        student_id = cursor.lastrowid
        cursor.close()
        flash("Student added successfully", "success")
        return redirect(url_for('student_summary', student_id=student_id))
    else:
        return render_template("add_student.html", today=datetime.today().strftime('%Y-%m-%d'))


@app.route("/edit_student/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):
    cursor = db.get_cursor()
    # Get common data
    query_dances = "SELECT * FROM dancetype;"
    cursor.execute(query_dances)
    dancetypes = cursor.fetchall()

    query_grades = "SELECT * FROM grades ORDER BY grade_level;"
    cursor.execute(query_grades)
    grades = cursor.fetchall()

    # Get student
    query_student = "SELECT * FROM students WHERE student_id = %s;"
    cursor.execute(query_student, (student_id,))
    student = cursor.fetchone()
    if not student:
        flash("Student not found", "error")
        return redirect(url_for('student_list'))
    student['dob_str'] = student['date_of_birth'].strftime('%Y-%m-%d') if student['date_of_birth'] else ''

    # Get current grades
    current_grades = {}
    query_current = "SELECT dancetype_id, grade_id FROM studentgrades WHERE student_id = %s;"
    cursor.execute(query_current, (student_id,))
    for row in cursor.fetchall():
        current_grades[row['dancetype_id']] = row['grade_id']

    if request.method == "POST":
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        dob_str = request.form.get('date_of_birth')

        # Validation
        if not first_name or not last_name:
            flash("First and last name are required", "error")
            cursor.close()
            return render_template("edit_student.html", student=student, dancetypes=dancetypes, grades=grades,
                                   current_grades=current_grades)

        try:
            dob = datetime.strptime(dob_str, '%Y-%m-%d') if dob_str else None
        except ValueError:
            flash("Invalid date format", "error")
            cursor.close()
            return render_template("edit_student.html", student=student, dancetypes=dancetypes, grades=grades,
                                   current_grades=current_grades)

        # Update student
        query_update = """
                       UPDATE students \
                       SET first_name    = %s, \
                           last_name     = %s, \
                           email         = %s, \
                           phone         = %s, \
                           date_of_birth = %s
                       WHERE student_id = %s; \
                       """
        cursor.execute(query_update, (first_name, last_name, email, phone, dob, student_id))

        # Update grades: delete all, then insert selected
        query_delete_grades = "DELETE FROM studentgrades WHERE student_id = %s;"
        cursor.execute(query_delete_grades, (student_id,))

        for dance in dancetypes:
            grade_id = request.form.get(f'grade_{dance["dancetype_id"]}')
            if grade_id:
                query_insert_grade = "INSERT INTO studentgrades (student_id, grade_id, dancetype_id) VALUES (%s, %s, %s);"
                cursor.execute(query_insert_grade, (student_id, grade_id, dance['dancetype_id']))

        db.get_db().commit()
        cursor.close()
        flash("Student updated successfully", "success")
        return redirect(url_for('student_summary', student_id=student_id))

    cursor.close()
    return render_template("edit_student.html", student=student, dancetypes=dancetypes, grades=grades,
                           current_grades=current_grades)


@app.route("/teacher_report")
def teacher_report():
    cursor = db.get_cursor()
    # Get class counts per teacher
    query_classes = """
                    SELECT t.teacher_id, \
                           t.first_name, \
                           t.last_name, \
                           c.class_id, \
                           c.class_name, \
                           COUNT(sc.student_id) AS student_count
                    FROM teachers t
                             LEFT JOIN classes c ON t.teacher_id = c.teacher_id
                             LEFT JOIN studentclasses sc ON c.class_id = sc.class_id
                    GROUP BY t.teacher_id, c.class_id
                    ORDER BY t.last_name, t.first_name, c.class_name; \
                    """
    cursor.execute(query_classes)
    class_data = cursor.fetchall()

    # Get unique students per teacher
    query_unique = """
                   SELECT t.teacher_id, COUNT(DISTINCT sc.student_id) AS unique_count
                   FROM teachers t
                            LEFT JOIN classes c ON t.teacher_id = c.teacher_id
                            LEFT JOIN studentclasses sc ON c.class_id = sc.class_id
                   GROUP BY t.teacher_id; \
                   """
    cursor.execute(query_unique)
    unique_data = {row['teacher_id']: row['unique_count'] for row in cursor.fetchall()}

    # Group in Python
    teacher_data = {}
    for row in class_data:
        tid = row['teacher_id']
        if tid not in teacher_data:
            teacher_data[tid] = {
                'name': f"{row['first_name']} {row['last_name']}",
                'classes': [],
                'total_unique': unique_data.get(tid, 0)
            }
        if row['class_id']:  # Skip if no classes
            teacher_data[tid]['classes'].append({
                'class_name': row['class_name'],
                'student_count': row['student_count']
            })

    cursor.close()
    return render_template("teacher_report.html", teacher_data=teacher_data.values())