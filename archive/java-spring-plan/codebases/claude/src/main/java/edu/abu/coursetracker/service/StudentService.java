package edu.abu.coursetracker.service;

import edu.abu.coursetracker.dto.StudentRequest;
import edu.abu.coursetracker.dto.StudentResponse;
import edu.abu.coursetracker.exception.ConflictException;
import edu.abu.coursetracker.exception.ResourceNotFoundException;
import edu.abu.coursetracker.model.Student;
import edu.abu.coursetracker.repository.StudentRepository;
import java.util.List;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StudentService {

    private final StudentRepository repository;

    public StudentService(StudentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public StudentResponse create(StudentRequest request) {
        if (repository.existsByStudentNumber(request.studentNumber())) {
            throw numberInUse(request.studentNumber());
        }
        Student student = new Student();
        apply(student, request);
        return save(student);
    }

    @Transactional(readOnly = true)
    public List<StudentResponse> findAll() {
        return repository.findAll(Sort.by("id")).stream().map(StudentResponse::from).toList();
    }

    @Transactional(readOnly = true)
    public StudentResponse get(Long id) {
        return StudentResponse.from(find(id));
    }

    @Transactional
    public StudentResponse update(Long id, StudentRequest request) {
        Student student = find(id);
        if (repository.existsByStudentNumberAndIdNot(request.studentNumber(), id)) {
            throw numberInUse(request.studentNumber());
        }
        apply(student, request);
        return save(student);
    }

    @Transactional
    public void delete(Long id) {
        repository.delete(find(id));
    }

    private Student find(Long id) {
        return repository.findById(id).orElseThrow(() -> new ResourceNotFoundException("Student", id));
    }

    private StudentResponse save(Student student) {
        try {
            return StudentResponse.from(repository.saveAndFlush(student));
        } catch (DataIntegrityViolationException e) {
            // Lost a race against a concurrent request using the same student number.
            throw numberInUse(student.getStudentNumber());
        }
    }

    private static void apply(Student student, StudentRequest request) {
        student.setStudentNumber(request.studentNumber());
        student.setFirstName(request.firstName());
        student.setLastName(request.lastName());
        student.setEmail(request.email());
    }

    private static ConflictException numberInUse(String studentNumber) {
        return new ConflictException("Student number " + studentNumber + " is already in use");
    }
}
