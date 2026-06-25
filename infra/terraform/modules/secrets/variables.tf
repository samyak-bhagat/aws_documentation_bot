variable "name_prefix" {
  type = string
}

variable "db_username" {
  type = string
}

variable "db_name" {
  type = string
}

variable "db_host" {
  type    = string
  default = ""
}

variable "db_port" {
  type    = number
  default = 5432
}
