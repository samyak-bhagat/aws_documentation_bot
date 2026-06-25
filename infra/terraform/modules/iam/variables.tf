variable "name_prefix" {
  type = string
}

variable "secret_arns" {
  type = list(string)
}

variable "enable_github_oidc" {
  type    = bool
  default = false
}

variable "github_repo" {
  type    = string
  default = ""
}
