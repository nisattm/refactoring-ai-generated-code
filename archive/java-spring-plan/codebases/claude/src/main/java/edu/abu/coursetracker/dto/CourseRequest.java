package edu.abu.coursetracker.dto;

import edu.abu.coursetracker.model.CourseType;
import edu.abu.coursetracker.model.GradingScheme;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CourseRequest(
        @NotNull(message = "is required")
        @Size(min = 2, max = 10, message = "must be 2 to 10 characters")
        @Pattern(regexp = "[A-Z0-9]*", message = "must contain only uppercase letters A-Z and digits")
        String code,

        @NotBlank(message = "is required and must not be blank")
        @Size(max = 100, message = "must be at most 100 characters")
        String name,

        @NotNull(message = "is required (THEORETICAL or PRACTICAL)")
        CourseType type,

        @NotNull(message = "is required")
        @Min(value = 1, message = "must be between 1 and 10")
        @Max(value = 10, message = "must be between 1 and 10")
        Integer weeklyHours,

        @NotNull(message = "is required (MIDTERM_FINAL or MIDTERM_PROJECT_FINAL)")
        GradingScheme gradingScheme) {
}
