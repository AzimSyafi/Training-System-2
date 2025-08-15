-- Create database and user for the training system
CREATE DATABASE security_training;
CREATE USER training_user WITH PASSWORD 'your_password_here';
GRANT ALL PRIVILEGES ON DATABASE security_training TO training_user;

-- Connect to the database and grant schema permissions
\c security_training;
GRANT ALL ON SCHEMA public TO training_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO training_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO training_user;
