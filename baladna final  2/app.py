import os
from calendar import monthrange
from datetime import datetime
import fitz  # PyMuPDF
import io
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from werkzeug.utils import secure_filename
import config


app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configuration for upload folder
UPLOAD_FOLDER = 'static/admin_pics'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Custom number format filter for Jinja2
def number_format(value, decimal_places=2):
    return f"{float(value):,.{decimal_places}f}"

app.jinja_env.filters['number_format'] = number_format

# Function to check if a file is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Function to calculate the equivalent number based on employee's extra hours
def calculate_equivalent_number(employee, extra_hours):
    salary_before = float(employee['monthly_salary'])
    num_days = monthrange(datetime.now().year, datetime.now().month)[1]
    salary_per_day = salary_before / num_days
    salary_per_hour = salary_per_day / 9
    return extra_hours * salary_per_hour

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
            session['admin'] = True
            if 'employees' not in session:
                session['employees'] = []  # Initialize the employee list in session
            if 'admins' not in session:
                session['admins'] = [{'username': config.ADMIN_USERNAME, 'password': config.ADMIN_PASSWORD, 'picture': None}]
            return redirect(url_for('admin_dashboard'))
        else:
            return "Invalid credentials, try again."
    return render_template('login.html')

@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        employees = session.get('employees', [])

        if 'add_employee' in request.form:
            name = request.form['name']
            monthly_salary = request.form['monthly_salary']
            phone_number = request.form['phone_number']
            id_number = request.form['id_number']
            start_date = request.form['start_date']
            address = request.form['address']

            try:
                parsed_start_date = datetime.strptime(start_date, '%d/%m/%Y')
            except ValueError:
                return "Invalid start date format. Please use DD/MM/YYYY."

            formatted_start_date = parsed_start_date.strftime('%d/%m/%Y')
            employee_id = len(employees) + 1

            employees.append({
                'id': employee_id,
                'name': name,
                'monthly_salary': monthly_salary,
                'phone_number': phone_number,
                'id_number': id_number,
                'start_date': formatted_start_date,
                'address': address,
                'holidays_taken': 0  # Initialize holidays taken
            })

        elif 'update_employee' in request.form:
            employee_id = int(request.form['employee_id'])
            new_salary = request.form['new_salary']
            new_phone_number = request.form['new_phone_number']
            new_address = request.form['new_address']

            for employee in employees:
                if employee['id'] == employee_id:
                    employee['monthly_salary'] = new_salary
                    employee['phone_number'] = new_phone_number
                    employee['address'] = new_address
                    break

        elif 'delete_employee' in request.form:
            employee_id = int(request.form['employee_id'])
            employees = [e for e in employees if e['id'] != employee_id]

        session['employees'] = employees
        return redirect(url_for('employee_list'))

    return render_template('admin_dashboard.html')


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'admin' not in session:
        return redirect(url_for('login'))

    admins = session.get('admins', [])

    if request.method == 'POST':
        if 'add_admin' in request.form:
            new_admin_username = request.form['username']
            new_admin_password = request.form['password']
            admin_picture = request.files['picture']

            if new_admin_username and new_admin_password and allowed_file(admin_picture.filename):
                filename = secure_filename(admin_picture.filename)
                picture_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                admin_picture.save(picture_path)

                admins.append({
                    'username': new_admin_username,
                    'password': new_admin_password,
                    'picture': picture_path
                })
                session['admins'] = admins
                flash("Admin added successfully!", "success")
            else:
                flash("Failed to add admin. Ensure all fields are filled and the picture is valid.", "danger")

        elif 'delete_admin' in request.form:
            admin_username = request.form['username']

            admins = [admin for admin in admins if admin['username'] != admin_username]

            session['admins'] = admins
            flash("Admin deleted successfully!", "success")

    return render_template('settings.html', admins=admins)

@app.route('/employee_list')
def employee_list():
    if 'admin' not in session:
        return redirect(url_for('login'))

    employees = session.get('employees', [])

    # Format the salary before passing it to the template
    for employee in employees:
        employee['formatted_salary'] = f"{float(employee['monthly_salary']):,.2f}"

    return render_template('employee_list.html', employees=employees)

@app.route('/employee_history/<int:employee_id>')
def employee_history(employee_id):
    if 'admin' not in session:
        return redirect(url_for('login'))

    employees = session.get('employees', [])
    employee = next((e for e in employees if e['id'] == employee_id), None)

    if not employee:
        return "Employee not found."

    # Directory where PDFs are stored
    sanitized_name = employee['name'].replace(" ", "_")
    pdf_directory = os.path.join('static', 'employees', sanitized_name)

    # Find all PDF files for this employee
    pdf_files = []
    if os.path.exists(pdf_directory):
        pdf_files = [f for f in os.listdir(pdf_directory) if f.endswith(".pdf")]

    # Ensure that the formatted salary is prepared
    employee['formatted_salary'] = f"{float(employee['monthly_salary']):,.2f}"

    # Create URLs for the PDF files
    pdf_urls = [url_for('static', filename=f'employees/{sanitized_name}/{pdf_file}') for pdf_file in pdf_files]

    return render_template('employee_history.html', employee=employee, pdf_files=zip(pdf_files, pdf_urls))



@app.route('/employee_details/<int:employee_id>', methods=['GET', 'POST'])
def employee_details(employee_id):
    if 'admin' not in session:
        return redirect(url_for('login'))

    employees = session.get('employees', [])
    employee = next((e for e in employees if e['id'] == employee_id), None)

    if not employee:
        return "Employee not found."

    now = datetime.now()
    current_month = now.strftime('%B %Y')
    num_days = monthrange(now.year, now.month)[1]

    salary_before = float(employee['monthly_salary'])
    salary_per_day = round(salary_before / num_days, 2)
    salary_per_hour = round(salary_per_day / 9, 2)

    days_absent = employee.get('days_absent', 0)
    extra_days = employee.get('extra_days', 0)
    hours_absent = employee.get('hours_absent', 0)
    extra_hours = employee.get('extra_hours', 0)
    advanced_payment = employee.get('advanced_payment', 0.0)
    holidays_taken = employee.get('holidays_taken', 0)  # New field for holidays taken
    holidays_value = f"{holidays_taken}/14"  # Display as taken/total
    salary_after = employee.get('salary_after', salary_before)

    if request.method == 'POST':
        days_absent = int(request.form['days_absent'])
        hours_absent = int(request.form['hours_absent'])
        extra_days = int(request.form['extra_days'])
        extra_hours = int(request.form['extra_hours'])
        advanced_payment = float(request.form['advanced_payment'])
        holidays_taken = int(request.form['holidays_taken'])  # Update holidays taken

        salary_after = (
            salary_before - advanced_payment
            - days_absent * salary_per_day
            - hours_absent * salary_per_hour
            + extra_days * salary_per_day
            + extra_hours * salary_per_hour
        )
        salary_after = round(salary_after, 2)

        employee.update({
            'days_absent': days_absent,
            'hours_absent': hours_absent,
            'extra_days': extra_days,
            'extra_hours': extra_hours,
            'advanced_payment': advanced_payment,
            'holidays_taken': holidays_taken,  # Save the updated holidays taken
            'salary_after': salary_after,
        })

        session['employees'] = employees

        return redirect(url_for('employee_details', employee_id=employee_id))

    return render_template('employee_details.html',
                           employee=employee,
                           current_month=current_month,
                           num_days=num_days,
                           salary_before=round(salary_before, 2),
                           salary_per_day=salary_per_day,
                           salary_per_hour=salary_per_hour,
                           days_absent=days_absent,
                           hours_absent=hours_absent,
                           extra_days=extra_days,
                           extra_hours=extra_hours,
                           advanced_payment=round(advanced_payment, 2),
                           holidays_value=holidays_value,
                           salary_after=salary_after)

@app.route('/generate_pdf/<int:employee_id>', methods=['GET'])
def generate_pdf(employee_id):
    if 'admin' not in session:
        return redirect(url_for('login'))

    employees = session.get('employees', [])
    employee = next((e for e in employees if e['id'] == employee_id), None)

    if not employee:
        return "Employee not found."

    try:
        extra_hours = employee.get('extra_hours', 0)
        extra_days = employee.get('extra_days', 0)
        days_absent = employee.get('days_absent', 0)
        equivalent_hours = calculate_equivalent_number(employee, extra_hours)
        equivalent_days = extra_days * (float(employee['monthly_salary']) / monthrange(datetime.now().year, datetime.now().month)[1])
        equivalent_days_absent = days_absent * (float(employee['monthly_salary']) / monthrange(datetime.now().year, datetime.now().month)[1])

        template_path = os.path.join('static', 'baldna salaries.pdf')
        if not os.path.exists(template_path):
            return "Template file not found."

        doc = fitz.open(template_path)
        page = doc[0]

        def insert_text(position, text, font_size=12, font_color=(0, 0, 0)):
            page.insert_text(position, text, fontsize=font_size, color=font_color)

        font_size = 12
        font_color = (0, 0, 0)

        insert_text((110, 208), datetime.now().strftime('%d/%m/%Y'), font_size, font_color)
        insert_text((370, 248), employee['name'], font_size, font_color)
        insert_text((380, 276), employee['id_number'], font_size, font_color)
        insert_text((390, 304), employee['address'], font_size, font_color)
        insert_text((235, 390), str(employee['monthly_salary']), font_size, font_color)
        insert_text((255, 417), str(employee.get('extra_hours', 0)), font_size, font_color)
        insert_text((158, 417), f"{equivalent_hours:.2f}", font_size, font_color)
        insert_text((265, 445), str(employee.get('extra_days', 0)), font_size, font_color)
        insert_text((159, 445), f"{equivalent_days:.2f}", font_size, font_color)
        insert_text((280, 472), str(employee.get('days_absent', 0)), font_size, font_color)
        insert_text((175, 472), f"{equivalent_days_absent:.2f}", font_size, font_color)  
        insert_text((312, 500), str(employee.get('advanced_payment', 0)), font_size, font_color)
        insert_text((260, 555), str(employee.get('salary_after', 0)), font_size, font_color)

        pdf_bytes = io.BytesIO()
        doc.save(pdf_bytes)
        pdf_bytes.seek(0)
        doc.close()

        return send_file(
            pdf_bytes,
            as_attachment=False,
            download_name=f"{employee['name']}_details.pdf",
            mimetype='application/pdf')

    except Exception as e:
        print(f"Error generating PDF: {e}")
        return "An error occurred while generating the PDF."
    


@app.route('/save_pdf/<int:employee_id>', methods=['GET'])
def save_pdf(employee_id):
    if 'admin' not in session:
        return redirect(url_for('login'))

    employees = session.get('employees', [])
    employee = next((e for e in employees if e['id'] == employee_id), None)

    if not employee:
        return "Employee not found."

    try:
        extra_hours = employee.get('extra_hours', 0)
        extra_days = employee.get('extra_days', 0)
        days_absent = employee.get('days_absent', 0)
        equivalent_hours = calculate_equivalent_number(employee, extra_hours)
        equivalent_days = extra_days * (float(employee['monthly_salary']) / monthrange(datetime.now().year, datetime.now().month)[1])
        equivalent_days_absent = days_absent * (float(employee['monthly_salary']) / monthrange(datetime.now().year, datetime.now().month)[1])

        template_path = os.path.join('static', 'baldna salaries.pdf')
        if not os.path.exists(template_path):
            return "Template file not found."

        doc = fitz.open(template_path)
        page = doc[0]

        def insert_text(position, text, font_size=12, font_color=(0, 0, 0)):
            page.insert_text(position, text, fontsize=font_size, color=font_color)

        font_size = 12
        font_color = (0, 0, 0)

        insert_text((110, 208), datetime.now().strftime('%d/%m/%Y'), font_size, font_color)
        insert_text((370, 248), employee['name'], font_size, font_color)
        insert_text((380, 276), employee['id_number'], font_size, font_color)
        insert_text((390, 304), employee['address'], font_size, font_color)
        insert_text((235, 390), str(employee['monthly_salary']), font_size, font_color)
        insert_text((255, 417), str(employee.get('extra_hours', 0)), font_size, font_color)
        insert_text((158, 417), f"{equivalent_hours:.2f}", font_size, font_color)
        insert_text((265, 445), str(employee.get('extra_days', 0)), font_size, font_color)
        insert_text((159, 445), f"{equivalent_days:.2f}", font_size, font_color)
        insert_text((280, 472), str(employee.get('days_absent', 0)), font_size, font_color)
        insert_text((175, 472), f"{equivalent_days_absent:.2f}", font_size, font_color)  
        insert_text((312, 500), str(employee.get('advanced_payment', 0)), font_size, font_color)
        insert_text((260, 555), str(employee.get('salary_after', 0)), font_size, font_color)

        sanitized_name = employee['name'].replace(" ", "_")
        pdf_directory = os.path.join('static', 'employees', sanitized_name)
        if not os.path.exists(pdf_directory):
            os.makedirs(pdf_directory)

        # Generate the base filename
        current_month_year = datetime.now().strftime('%B_%Y')
        base_filename = f"{sanitized_name}_{current_month_year}"
        
        # Check if there are already PDFs with the same base name
        existing_files = [f for f in os.listdir(pdf_directory) if f.startswith(base_filename) and f.endswith(".pdf")]

        # Determine the next number to append
        if existing_files:
            max_num = max([int(f[len(base_filename)+1:-4]) for f in existing_files if f[len(base_filename)+1:-4].isdigit()] or [0])
            next_num = max_num + 1
        else:
            next_num = 1
        
        # Final filename with number appended
        pdf_filename = f"{base_filename}_{next_num}.pdf"
        pdf_filepath = os.path.join(pdf_directory, pdf_filename)
        
        doc.save(pdf_filepath)
        doc.close()

        return f"PDF saved successfully as {pdf_filename}."

    except Exception as e:
        print(f"Error saving PDF: {e}")
        return "An error occurred while saving the PDF."


if __name__ == '__main__':
    app.run(debug=True)
