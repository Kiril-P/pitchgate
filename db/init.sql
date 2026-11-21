-- Local only: one database per service and one login per service that can reach only its own database.
-- Safe to run on every `docker compose up`: each step checks before it creates.
-- Passwords arrive as sqlcmd variables from the compose file, never written here.
-- On Azure the same split is made once with contained users (see README, initial setup).

IF DB_ID('ideas') IS NULL CREATE DATABASE ideas;
IF DB_ID('review') IS NULL CREATE DATABASE review;
GO

IF SUSER_ID('ideas_app') IS NULL CREATE LOGIN ideas_app WITH PASSWORD = '$(IDEAS_DB_PASSWORD)', CHECK_POLICY = ON;
ELSE ALTER LOGIN ideas_app WITH PASSWORD = '$(IDEAS_DB_PASSWORD)';
IF SUSER_ID('review_app') IS NULL CREATE LOGIN review_app WITH PASSWORD = '$(REVIEW_DB_PASSWORD)', CHECK_POLICY = ON;
ELSE ALTER LOGIN review_app WITH PASSWORD = '$(REVIEW_DB_PASSWORD)';
GO

USE ideas;
IF USER_ID('ideas_app') IS NULL CREATE USER ideas_app FOR LOGIN ideas_app;
IF IS_ROLEMEMBER('db_ddladmin', 'ideas_app') = 0 ALTER ROLE db_ddladmin ADD MEMBER ideas_app;
IF IS_ROLEMEMBER('db_datareader', 'ideas_app') = 0 ALTER ROLE db_datareader ADD MEMBER ideas_app;
IF IS_ROLEMEMBER('db_datawriter', 'ideas_app') = 0 ALTER ROLE db_datawriter ADD MEMBER ideas_app;
GO

USE review;
IF USER_ID('review_app') IS NULL CREATE USER review_app FOR LOGIN review_app;
IF IS_ROLEMEMBER('db_ddladmin', 'review_app') = 0 ALTER ROLE db_ddladmin ADD MEMBER review_app;
IF IS_ROLEMEMBER('db_datareader', 'review_app') = 0 ALTER ROLE db_datareader ADD MEMBER review_app;
IF IS_ROLEMEMBER('db_datawriter', 'review_app') = 0 ALTER ROLE db_datawriter ADD MEMBER review_app;
GO
