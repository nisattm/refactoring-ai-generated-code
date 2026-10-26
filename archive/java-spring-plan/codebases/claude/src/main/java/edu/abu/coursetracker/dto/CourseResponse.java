package edu.abu.coursetracker.dto;

import edu.abu.coursetracker.model.Course;
import edu.abu.coursetracker.model.CourseType;
import edu.abu.coursetracker.model.GradingScheme;

public record CourseResponse(
        Long id, String code, String name, CourseType type, int weeklyHours, GradingScheme gradingScheme) {

    public static CourseResponse from(Course c) {
        return new CourseResponse(c.getId(), c.getCode(), c.getName(), c.getType(), c.getWeeklyHours(), c.getGradingScheme());
    }
}
