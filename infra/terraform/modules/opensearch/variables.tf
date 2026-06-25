variable "name_prefix" {
  type = string
}

variable "domain_name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "app_security_group_id" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "aws_account_id" {
  type = string
}

variable "allowed_principal_arns" {
  type = list(string)
}

variable "master_user_name" {
  type    = string
  default = "admin"
}

variable "master_user_password" {
  type      = string
  sensitive = true
}

variable "instance_type" {
  type    = string
  default = "t3.small.search"
}

variable "instance_count" {
  type    = number
  default = 1
}

variable "ebs_volume_size" {
  type    = number
  default = 20
}
