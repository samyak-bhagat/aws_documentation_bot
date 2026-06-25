resource "random_password" "db" {
  length  = 32
  special = false
}

resource "random_password" "jwt" {
  length  = 48
  special = true
}

resource "aws_secretsmanager_secret" "db" {
  name = "${var.name_prefix}/database"
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id

  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    engine   = "postgres"
    host     = var.db_host
    port     = var.db_port
    dbname   = var.db_name
    url      = "postgresql+asyncpg://${var.db_username}:${random_password.db.result}@${var.db_host}:${var.db_port}/${var.db_name}"
  })
}

resource "aws_secretsmanager_secret" "jwt" {
  name = "${var.name_prefix}/jwt"
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id = aws_secretsmanager_secret.jwt.id

  secret_string = jsonencode({
    jwt_secret = random_password.jwt.result
  })
}
