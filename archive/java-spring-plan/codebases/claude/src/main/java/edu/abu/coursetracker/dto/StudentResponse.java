package edu.abu.coursetracker.dto;

import edu.abu.coursetracker.model.Student;

public record StudentResponse(Long id, String studentNumber, String firstName, String lastName, String email) {

    public static StudentResponse from(Student s) {
        return new StudentResponse(s.getId(), s.getStudentNumber(), s.getFirstName(), s.getLastName(), s.getEmail());
    }
}
