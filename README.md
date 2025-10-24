# Login System

## Overview

This repository contains a PHP-based login system designed to provide secure authentication and user management functionality for web applications. It supports user registration, login, session management, account activation, password recovery, and admin functionalities.

## Features

- Allows new users to register by providing their username, email, and password
- Authenticates users based on their credentials and initiates a session
- Terminates the user's session and redirects to the login page
- Manages user sessions to ensure secure access to restricted areas
- Sends account activation emails and password reset links
- Allows users to reset their password through a secure process
- Enables users to update their email and other account information
- Provides administrative controls for managing user accounts
- Visualizes user login data and other relevant statistics using JavaScript charts
- Enhances the system with asynchronous data loading and session timeouts for improved user experience

## Requirements

- PHP (version 7.4 or higher recommended)
- MySQL or MariaDB
- PHPMailer

## Installation

1. Clone the repository or download the source code

2. Ensure that PHP and MySQL/MariaDB are installed on your server. Here are guides to install [PHP](https://www.php.net/manual/en/install.php) and [MySQL](https://dev.mysql.com/doc/refman/8.0/en/installing.html)

3. Download PHPMailer from [PHPMailer](https://github.com/PHPMailer/PHPMailer) and place it in the main directory

4. Import the SQL schema to set up your database tables:

```
mysql -u username -p database_name < user_accounts.sql
```

5. Edit the `config.php` file with your database settings and `activationmail.php` with your PHPMailer settings

6. **(Optional)**: If you want to populate your database with sample data to test the functionality of the login system, import the `randomusers.sql` file:

```
mysql -u username -p database_name < randomusers.sql
```

## Usage

To start using the login system, direct your browser to the installation path. Users can register a new account or log in using their existing credentials.

Refer to individual script comments for more detailed instructions on each feature.

## Contributing

Contributions to this repository are welcome! If you have an idea for a new tool or an improvement to an existing tool, feel free to create a pull request or open an issue.

## License

This project is licensed under the [GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.en.html).
