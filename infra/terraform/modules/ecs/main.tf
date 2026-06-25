resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name_prefix}/api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "ui" {
  name              = "/ecs/${var.name_prefix}/ui"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name  = "api"
    image = var.api_image
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]
    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "BEDROCK_REGION", value = var.aws_region },
      { name = "BEDROCK_MODEL_ID", value = var.bedrock_model_id },
      { name = "BEDROCK_EMBED_MODEL_ID", value = var.bedrock_embed_model_id },
      { name = "OPENSEARCH_ENDPOINT", value = var.opensearch_endpoint },
      { name = "OPENSEARCH_INDEX", value = var.opensearch_index },
      { name = "MCP_SERVER_COMMAND", value = "uvx" },
      { name = "MCP_SERVER_ARGS", value = "awslabs.aws-documentation-mcp-server@latest" },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = "${var.db_secret_arn}:url::" },
      { name = "JWT_SECRET", valueFrom = "${var.jwt_secret_arn}:jwt_secret::" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
    essential = true
  }])
}

resource "aws_ecs_task_definition" "ui" {
  family                   = "${var.name_prefix}-ui"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ui_cpu
  memory                   = var.ui_memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name  = "ui"
    image = var.ui_image
    portMappings = [{
      containerPort = 8501
      protocol      = "tcp"
    }]
    environment = [
      { name = "API_URL", value = "http://${var.internal_api_url}" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ui.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ui"
      }
    }
    essential = true
  }])
}

resource "aws_ecs_service" "api" {
  name            = "${var.name_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = var.assign_public_ip
  }

  load_balancer {
    target_group_arn = var.api_target_group_arn
    container_name   = "api"
    container_port   = 8000
  }
}

resource "aws_ecs_service" "ui" {
  name            = "${var.name_prefix}-ui"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.ui.arn
  desired_count   = var.ui_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = var.assign_public_ip
  }

  load_balancer {
    target_group_arn = var.ui_target_group_arn
    container_name   = "ui"
    container_port   = 8501
  }
}
