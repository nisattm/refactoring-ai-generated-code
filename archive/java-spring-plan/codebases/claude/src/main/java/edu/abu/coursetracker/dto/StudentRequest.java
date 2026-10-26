package edu.abu.coursetracker.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record StudentRequest(
        @NotNull(message = "is required")
        @Pattern(regexp = "[0-9]{9}", message = "must be exactly 9 digits")
        String studentNumber,

        @NotBlank(message = "is required and must not be blank")
        @Size(max = 50, message = "must be at most 50 characters")
        String firstName,

        @NotBlank(message = "is required and must not be blank")
        @Size(max = 50, message = "must be at most 50 characters")
        String lastName,

        @NotBlank(message = "is required and must not be blank")
        @Size(max = 254, message = "must be at most 254 characters")
        @Email(message = "must be a well-formed email address")
        String email) {
}
